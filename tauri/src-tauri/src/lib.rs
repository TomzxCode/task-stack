//! Task Stack — Tauri application entry point.
//!
//! Coordinates the tray icon, the global hotkey, and the stack window. The
//! active task stack lives in [`stack::Store`] (behind a mutex in
//! [`AppState`]); all mutations persist to disk and refresh the tray.

mod hotkey;
mod icon;
mod settings;
mod stack;

use std::collections::HashSet;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use chrono::Local;
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use stack::{Store, TaskView};

pub struct AppState {
    store: Mutex<Store>,
    hotkey_pretty: Mutex<String>,
    geometry_gen: AtomicU64,
    tray: Mutex<Option<TrayIcon>>,
}

fn now() -> chrono::DateTime<Local> {
    Local::now()
}

fn emit_all(app: &AppHandle, event: &str) {
    let _ = app.emit(event, ());
}

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

fn build_tray_menu(
    app: &AppHandle,
    current: Option<&str>,
    has_tasks: bool,
    hotkey_pretty: &str,
) -> tauri::Result<Menu<tauri::Wry>> {
    let current_label = current.unwrap_or("No tasks");
    let open_label = if hotkey_pretty.is_empty() {
        "Open Stack".to_string()
    } else {
        format!("Open Stack ({hotkey_pretty})")
    };

    let current_item = MenuItem::with_id(app, "current", current_label, false, None::<&str>)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let open_item = MenuItem::with_id(app, "open", open_label, true, None::<&str>)?;
    let pop_item = MenuItem::with_id(app, "pop", "Mark Done (pop)", has_tasks, None::<&str>)?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let help_item = MenuItem::with_id(app, "help", "Keyboard Shortcuts", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    Menu::with_items(
        app,
        &[
            &current_item,
            &sep1,
            &open_item,
            &pop_item,
            &sep2,
            &help_item,
            &quit_item,
        ],
    )
}

fn tray_icon_image(count: usize) -> Image<'static> {
    let thresholds = settings::load().resolved_icon_thresholds();
    let (rgba, w, h) = icon::make_icon(count, &thresholds);
    Image::new_owned(rgba, w, h)
}

/// Rebuild the tray icon image, menu and tooltip from the current store state.
fn refresh_tray(app: &AppHandle) {
    let state = app.state::<AppState>();
    let (count, current) = {
        let store = state.store.lock().unwrap();
        (store.count(), store.current_text())
    };
    let hotkey_pretty = state.hotkey_pretty.lock().unwrap().clone();

    let guard = state.tray.lock().unwrap();
    let tray = match guard.as_ref() {
        Some(t) => t,
        None => return,
    };

    let _ = tray.set_icon(Some(tray_icon_image(count)));
    let tooltip = current.clone().unwrap_or_else(|| "No tasks".to_string());
    let _ = tray.set_tooltip(Some(&tooltip));
    if let Ok(menu) = build_tray_menu(app, current.as_deref(), count > 0, &hotkey_pretty) {
        let _ = tray.set_menu(Some(menu));
    }
}

// ---------------------------------------------------------------------------
// Window helpers
// ---------------------------------------------------------------------------

fn window_is_visible(app: &AppHandle) -> bool {
    app.get_webview_window("main")
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

fn show_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
        // Reload in case the stack changed while hidden (e.g. tray pop).
        emit_all(app, "stack-changed");
    }
}

fn hide_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        save_geometry_now(&win);
        let _ = win.hide();
    }
}

fn toggle_window(app: &AppHandle) {
    if window_is_visible(app) {
        hide_window(app);
    } else {
        show_window(app);
    }
}

fn save_geometry_now(win: &tauri::WebviewWindow) {
    if let (Ok(pos), Ok(size)) = (win.outer_position(), win.outer_size()) {
        if size.width <= 1 || size.height <= 1 {
            return;
        }
        let geom = settings::WindowGeometry {
            width: size.width as i64,
            height: size.height as i64,
            x: pos.x as i64,
            y: pos.y as i64,
        };
        let mut s = settings::load();
        let unchanged = s
            .window
            .map(|g| g.width == geom.width && g.height == geom.height && g.x == geom.x && g.y == geom.y)
            .unwrap_or(false);
        if unchanged {
            return;
        }
        s.window = Some(geom);
        settings::save(&s);
    }
}

/// Debounced geometry save: bump a generation counter and persist only if no
/// further move/resize arrives within the debounce window.
fn schedule_geometry_save(app: &AppHandle) {
    let state = app.state::<AppState>();
    let generation = state.geometry_gen.fetch_add(1, Ordering::SeqCst) + 1;
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(400));
        let state = app.state::<AppState>();
        if state.geometry_gen.load(Ordering::SeqCst) != generation {
            return; // superseded by a newer event
        }
        if let Some(win) = app.get_webview_window("main") {
            if win.is_visible().unwrap_or(false) {
                save_geometry_now(&win);
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

#[derive(serde::Serialize)]
pub struct SettingsView {
    hotkey: String,
    hotkey_pretty: String,
    font_family: String,
    font_size: i64,
}

#[tauri::command]
fn get_settings(state: State<AppState>) -> SettingsView {
    let s = settings::load();
    let pretty = state.hotkey_pretty.lock().unwrap().clone();
    SettingsView {
        hotkey: s.hotkey,
        hotkey_pretty: pretty,
        font_family: s.font_family,
        font_size: s.font_size,
    }
}

#[tauri::command]
fn list_tasks(state: State<AppState>) -> Vec<TaskView> {
    state.store.lock().unwrap().views()
}

fn mutate<F: FnOnce(&mut Store)>(app: &AppHandle, state: &State<AppState>, f: F) -> Vec<TaskView> {
    let views = {
        let mut store = state.store.lock().unwrap();
        f(&mut store);
        store.views()
    };
    refresh_tray(app);
    views
}

#[tauri::command]
fn push(app: AppHandle, state: State<AppState>, text: String) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.push(&text, now()))
}

#[tauri::command]
fn push_next(app: AppHandle, state: State<AppState>, text: String) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.push_next(&text, now()))
}

#[tauri::command]
fn push_last(app: AppHandle, state: State<AppState>, text: String) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.push_last(&text, now()))
}

#[tauri::command]
fn pop(app: AppHandle, state: State<AppState>) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.pop(now()))
}

#[tauri::command]
fn promote(app: AppHandle, state: State<AppState>, idx: usize) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.promote(idx, now()))
}

#[tauri::command]
fn reorder(app: AppHandle, state: State<AppState>, from_idx: usize, to_idx: usize) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.reorder(from_idx, to_idx, now()))
}

#[derive(serde::Serialize)]
pub struct ReorderGroupResult {
    tasks: Vec<TaskView>,
    /// pairs of [old_index, new_index]
    index_map: Vec<[usize; 2]>,
}

#[tauri::command]
fn reorder_group(
    app: AppHandle,
    state: State<AppState>,
    from_indices: Vec<usize>,
    anchor_idx: usize,
    target_idx: usize,
) -> ReorderGroupResult {
    let set: HashSet<usize> = from_indices.into_iter().collect();
    let (views, map) = {
        let mut store = state.store.lock().unwrap();
        let m = store.reorder_group(&set, anchor_idx, target_idx, now());
        (store.views(), m)
    };
    refresh_tray(&app);
    let mut index_map: Vec<[usize; 2]> = map.into_iter().map(|(k, v)| [k, v]).collect();
    index_map.sort_unstable();
    ReorderGroupResult { tasks: views, index_map }
}

#[tauri::command]
fn update_text(app: AppHandle, state: State<AppState>, idx: usize, text: String) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.update_text(idx, &text))
}

#[tauri::command]
fn update_description(
    app: AppHandle,
    state: State<AppState>,
    idx: usize,
    description: String,
) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.update_description(idx, &description))
}

#[tauri::command]
fn remove(app: AppHandle, state: State<AppState>, idx: usize) -> Vec<TaskView> {
    mutate(&app, &state, |s| s.remove(idx, now()))
}

#[tauri::command]
fn remove_many(app: AppHandle, state: State<AppState>, indices: Vec<usize>) -> Vec<TaskView> {
    let set: HashSet<usize> = indices.into_iter().collect();
    mutate(&app, &state, |s| s.remove_many(&set, now()))
}

#[tauri::command]
fn request_hide(app: AppHandle) {
    hide_window(&app);
}

#[tauri::command]
fn open_url(app: AppHandle, url: String) {
    use tauri_plugin_opener::OpenerExt;
    let _ = app.opener().open_url(url, None::<&str>);
}

// ---------------------------------------------------------------------------
// App bootstrap
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let store = Store::load();

    // Resolve the configured hotkey (falling back to the default).
    let cfg = settings::load();
    let parsed = hotkey::parse_or_default(&cfg.hotkey, settings::DEFAULT_HOTKEY);
    let hotkey_pretty = parsed.pretty.clone();
    let shortcut = parsed.shortcut;
    let shortcut_for_handler = shortcut;

    let state = AppState {
        store: Mutex::new(store),
        hotkey_pretty: Mutex::new(hotkey_pretty),
        geometry_gen: AtomicU64::new(0),
        tray: Mutex::new(None),
    };

    let gs_plugin = tauri_plugin_global_shortcut::Builder::new()
        .with_handler(move |app, scut, event| {
            if *scut == shortcut_for_handler && event.state() == ShortcutState::Pressed {
                toggle_window(app);
            }
        })
        .build();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(gs_plugin)
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            get_settings,
            list_tasks,
            push,
            push_next,
            push_last,
            pop,
            promote,
            reorder,
            reorder_group,
            update_text,
            update_description,
            remove,
            remove_many,
            request_hide,
            open_url,
        ])
        .setup(move |app| {
            let handle = app.handle().clone();

            // Register the global hotkey.
            if let Err(e) = app.global_shortcut().register(shortcut) {
                eprintln!("task-stack: failed to register hotkey: {e}");
            }

            // Build the tray icon, menu and event handlers.
            let (count, current, hotkey_pretty) = {
                let state = handle.state::<AppState>();
                let store = state.store.lock().unwrap();
                let pretty = state.hotkey_pretty.lock().unwrap().clone();
                (store.count(), store.current_text(), pretty)
            };
            let menu = build_tray_menu(&handle, current.as_deref(), count > 0, &hotkey_pretty)?;
            let menu_handle = handle.clone();
            let icon_handle = handle.clone();
            let tray = TrayIconBuilder::with_id("main")
                .icon(tray_icon_image(count))
                .tooltip(current.as_deref().unwrap_or("No tasks"))
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(move |_tray, event| match event.id().as_ref() {
                    "open" => show_window(&menu_handle),
                    "pop" => {
                        {
                            let state = menu_handle.state::<AppState>();
                            let mut store = state.store.lock().unwrap();
                            store.pop(now());
                        }
                        refresh_tray(&menu_handle);
                        emit_all(&menu_handle, "stack-changed");
                    }
                    "help" => {
                        show_window(&menu_handle);
                        emit_all(&menu_handle, "show-help");
                    }
                    "quit" => menu_handle.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_window(&icon_handle);
                    }
                })
                .build(app)?;

            *handle.state::<AppState>().tray.lock().unwrap() = Some(tray);

            // Apply saved geometry and install window lifecycle handlers.
            if let Some(win) = app.get_webview_window("main") {
                if let Some(g) = cfg.window {
                    let _ = win.set_size(tauri::PhysicalSize::new(g.width as u32, g.height as u32));
                    let _ = win.set_position(tauri::PhysicalPosition::new(g.x as i32, g.y as i32));
                }
                let h = handle.clone();
                win.on_window_event(move |event| match event {
                    WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close();
                        hide_window(&h);
                    }
                    WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                        schedule_geometry_save(&h);
                    }
                    _ => {}
                });
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running task-stack");
}
