//! Parse a user-friendly hotkey spec into a Tauri global `Shortcut`.
//!
//! Port of the original `task_stack.hotkey` parser. Format is a `+`-separated
//! list of tokens, e.g. `ctrl+shift+t`, `alt+space`, `cmd+/`. Exactly one
//! non-modifier key plus one or more modifiers.

use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut};

#[derive(Debug)]
pub struct HotkeyParseError(#[allow(dead_code)] pub String);

pub struct ParsedHotkey {
    pub shortcut: Shortcut,
    pub pretty: String,
}

fn modifier_alias(token: &str) -> Option<&'static str> {
    match token {
        "ctrl" | "control" => Some("ctrl"),
        "shift" => Some("shift"),
        "alt" | "option" | "opt" => Some("alt"),
        "cmd" | "command" | "super" | "win" | "meta" => Some("cmd"),
        _ => None,
    }
}

fn named_key(token: &str) -> Option<Code> {
    Some(match token {
        "space" => Code::Space,
        "tab" => Code::Tab,
        "enter" | "return" => Code::Enter,
        "esc" | "escape" => Code::Escape,
        "up" => Code::ArrowUp,
        "down" => Code::ArrowDown,
        "left" => Code::ArrowLeft,
        "right" => Code::ArrowRight,
        "home" => Code::Home,
        "end" => Code::End,
        "page_up" | "pageup" => Code::PageUp,
        "page_down" | "pagedown" => Code::PageDown,
        "insert" => Code::Insert,
        "delete" => Code::Delete,
        "backspace" => Code::Backspace,
        _ => return None,
    })
}

fn function_key(token: &str) -> Option<Code> {
    if token.len() < 2 || !token.starts_with('f') {
        return None;
    }
    let n: u32 = token[1..].parse().ok()?;
    Some(match n {
        1 => Code::F1,
        2 => Code::F2,
        3 => Code::F3,
        4 => Code::F4,
        5 => Code::F5,
        6 => Code::F6,
        7 => Code::F7,
        8 => Code::F8,
        9 => Code::F9,
        10 => Code::F10,
        11 => Code::F11,
        12 => Code::F12,
        13 => Code::F13,
        14 => Code::F14,
        15 => Code::F15,
        16 => Code::F16,
        17 => Code::F17,
        18 => Code::F18,
        19 => Code::F19,
        20 => Code::F20,
        21 => Code::F21,
        22 => Code::F22,
        23 => Code::F23,
        24 => Code::F24,
        _ => return None,
    })
}

fn char_key(token: &str) -> Option<Code> {
    let mut chars = token.chars();
    let c = chars.next()?;
    if chars.next().is_some() {
        return None;
    }
    Some(match c {
        'a' => Code::KeyA,
        'b' => Code::KeyB,
        'c' => Code::KeyC,
        'd' => Code::KeyD,
        'e' => Code::KeyE,
        'f' => Code::KeyF,
        'g' => Code::KeyG,
        'h' => Code::KeyH,
        'i' => Code::KeyI,
        'j' => Code::KeyJ,
        'k' => Code::KeyK,
        'l' => Code::KeyL,
        'm' => Code::KeyM,
        'n' => Code::KeyN,
        'o' => Code::KeyO,
        'p' => Code::KeyP,
        'q' => Code::KeyQ,
        'r' => Code::KeyR,
        's' => Code::KeyS,
        't' => Code::KeyT,
        'u' => Code::KeyU,
        'v' => Code::KeyV,
        'w' => Code::KeyW,
        'x' => Code::KeyX,
        'y' => Code::KeyY,
        'z' => Code::KeyZ,
        '0' => Code::Digit0,
        '1' => Code::Digit1,
        '2' => Code::Digit2,
        '3' => Code::Digit3,
        '4' => Code::Digit4,
        '5' => Code::Digit5,
        '6' => Code::Digit6,
        '7' => Code::Digit7,
        '8' => Code::Digit8,
        '9' => Code::Digit9,
        '/' => Code::Slash,
        '\\' => Code::Backslash,
        '.' => Code::Period,
        ',' => Code::Comma,
        ';' => Code::Semicolon,
        '\'' => Code::Quote,
        '`' => Code::Backquote,
        '-' => Code::Minus,
        '=' => Code::Equal,
        '[' => Code::BracketLeft,
        ']' => Code::BracketRight,
        _ => return None,
    })
}

fn title_case(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        Some(c) => c.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

pub fn parse(spec: &str) -> Result<ParsedHotkey, HotkeyParseError> {
    if spec.trim().is_empty() {
        return Err(HotkeyParseError("empty hotkey spec".into()));
    }
    let parts: Vec<String> = spec
        .split('+')
        .map(|p| p.trim().to_lowercase())
        .filter(|p| !p.is_empty())
        .collect();
    if parts.is_empty() {
        return Err(HotkeyParseError(format!("could not parse hotkey: {spec:?}")));
    }

    let mut modifiers = Modifiers::empty();
    let mut key_token: Option<String> = None;
    let mut pretty_parts: Vec<String> = Vec::new();

    for token in &parts {
        if let Some(mod_name) = modifier_alias(token) {
            match mod_name {
                "ctrl" => modifiers |= Modifiers::CONTROL,
                "shift" => modifiers |= Modifiers::SHIFT,
                "alt" => modifiers |= Modifiers::ALT,
                "cmd" => modifiers |= Modifiers::SUPER,
                _ => {}
            }
            pretty_parts.push(title_case(mod_name));
            continue;
        }
        if key_token.is_some() {
            return Err(HotkeyParseError(format!(
                "hotkey {spec:?} has more than one non-modifier key"
            )));
        }
        key_token = Some(token.clone());
        pretty_parts.push(if token.chars().count() == 1 {
            token.clone()
        } else {
            title_case(token)
        });
    }

    let key_token = key_token
        .ok_or_else(|| HotkeyParseError(format!("hotkey {spec:?} is missing a non-modifier key")))?;

    let code = named_key(&key_token)
        .or_else(|| function_key(&key_token))
        .or_else(|| char_key(&key_token))
        .ok_or_else(|| {
            HotkeyParseError(format!("unrecognized key token {key_token:?} in hotkey {spec:?}"))
        })?;

    if modifiers.is_empty() {
        return Err(HotkeyParseError(format!("hotkey {spec:?} needs at least one modifier")));
    }

    Ok(ParsedHotkey {
        shortcut: Shortcut::new(Some(modifiers), code),
        pretty: pretty_parts.join("+"),
    })
}

pub fn parse_or_default(spec: &str, default: &str) -> ParsedHotkey {
    parse(spec).unwrap_or_else(|_| parse(default).expect("default hotkey must parse"))
}
