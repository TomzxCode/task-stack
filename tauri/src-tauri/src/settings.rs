//! Persisted UI settings (window geometry, hotkey, font, icon thresholds).
//!
//! Port of the original `task_stack.settings` Python module. Stored as YAML in
//! `~/.task-stack.settings.yaml`, written atomically.

use std::path::PathBuf;

use serde::Serialize;
use serde_yaml::{Mapping, Value};

pub const DEFAULT_HOTKEY: &str = "ctrl+shift+t";
pub const DEFAULT_FONT_FAMILY: &str = "system-ui";
pub const DEFAULT_FONT_SIZE: i64 = 11;

/// Default thresholds: (min_count, (r, g, b)). First entry where
/// count >= min_count (descending) wins. count == 0 always uses grey.
pub const DEFAULT_THRESHOLDS: [(i64, (u8, u8, u8)); 3] =
    [(11, (200, 50, 50)), (6, (220, 180, 0)), (1, (70, 130, 180))];

fn home() -> PathBuf {
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("."))
}

fn settings_file() -> PathBuf {
    home().join(".task-stack.settings.yaml")
}

fn settings_tmp() -> PathBuf {
    home().join(".task-stack.settings.yaml.tmp")
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct WindowGeometry {
    pub width: i64,
    pub height: i64,
    pub x: i64,
    pub y: i64,
}

#[derive(Clone, Copy, Debug)]
pub struct IconThreshold {
    pub min_count: i64,
    pub color: (u8, u8, u8),
}

#[derive(Clone, Debug, Serialize)]
pub struct Settings {
    pub window: Option<WindowGeometry>,
    pub hotkey: String,
    pub font_family: String,
    pub font_size: i64,
    #[serde(skip)]
    pub icon_thresholds: Option<Vec<IconThreshold>>,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            window: None,
            hotkey: DEFAULT_HOTKEY.to_string(),
            font_family: DEFAULT_FONT_FAMILY.to_string(),
            font_size: DEFAULT_FONT_SIZE,
            icon_thresholds: None,
        }
    }
}

fn parse_hex(s: &str) -> Option<(u8, u8, u8)> {
    let h = s.trim_start_matches('#');
    if h.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&h[0..2], 16).ok()?;
    let g = u8::from_str_radix(&h[2..4], 16).ok()?;
    let b = u8::from_str_radix(&h[4..6], 16).ok()?;
    Some((r, g, b))
}

impl Settings {
    /// Thresholds resolved against defaults and sorted ascending by min_count.
    pub fn resolved_icon_thresholds(&self) -> Vec<(i64, (u8, u8, u8))> {
        let mut list: Vec<(i64, (u8, u8, u8))> = match &self.icon_thresholds {
            Some(ts) if !ts.is_empty() => ts.iter().map(|t| (t.min_count, t.color)).collect(),
            _ => DEFAULT_THRESHOLDS.to_vec(),
        };
        list.sort_by_key(|t| t.0);
        list
    }

    fn from_value(v: &Value) -> Settings {
        let m = match v.as_mapping() {
            Some(m) => m,
            None => return Settings::default(),
        };
        let window = m.get(Value::from("window")).and_then(|w| {
            let wm = w.as_mapping()?;
            let g = |k: &str| wm.get(Value::from(k)).and_then(|x| x.as_i64());
            Some(WindowGeometry {
                width: g("width")?,
                height: g("height")?,
                x: g("x")?,
                y: g("y")?,
            })
        });
        let hotkey = m
            .get(Value::from("hotkey"))
            .and_then(|x| x.as_str())
            .filter(|s| !s.trim().is_empty())
            .unwrap_or(DEFAULT_HOTKEY)
            .to_string();
        let font_family = m
            .get(Value::from("font_family"))
            .and_then(|x| x.as_str())
            .filter(|s| !s.trim().is_empty())
            .unwrap_or(DEFAULT_FONT_FAMILY)
            .to_string();
        let font_size = m
            .get(Value::from("font_size"))
            .and_then(|x| x.as_i64().or_else(|| x.as_f64().map(|f| f as i64)))
            .filter(|&n| (6..=72).contains(&n))
            .unwrap_or(DEFAULT_FONT_SIZE);
        let icon_thresholds = m
            .get(Value::from("icon_thresholds"))
            .and_then(|x| x.as_sequence())
            .map(|seq| {
                seq.iter()
                    .filter_map(|t| {
                        let tm = t.as_mapping()?;
                        let mc = tm.get(Value::from("min_count")).and_then(|x| x.as_i64())?;
                        let color = tm
                            .get(Value::from("color"))
                            .and_then(|x| x.as_str())
                            .and_then(parse_hex)?;
                        Some(IconThreshold { min_count: mc, color })
                    })
                    .collect::<Vec<_>>()
            })
            .filter(|v: &Vec<IconThreshold>| !v.is_empty());

        Settings {
            window,
            hotkey,
            font_family,
            font_size,
            icon_thresholds,
        }
    }

    fn to_value(&self) -> Value {
        let mut m = Mapping::new();
        m.insert(
            Value::from("window"),
            match self.window {
                Some(g) => {
                    let mut wm = Mapping::new();
                    wm.insert(Value::from("width"), Value::from(g.width));
                    wm.insert(Value::from("height"), Value::from(g.height));
                    wm.insert(Value::from("x"), Value::from(g.x));
                    wm.insert(Value::from("y"), Value::from(g.y));
                    Value::Mapping(wm)
                }
                None => Value::Null,
            },
        );
        m.insert(Value::from("hotkey"), Value::from(self.hotkey.clone()));
        m.insert(Value::from("font_family"), Value::from(self.font_family.clone()));
        m.insert(Value::from("font_size"), Value::from(self.font_size));
        m.insert(
            Value::from("icon_thresholds"),
            match &self.icon_thresholds {
                Some(ts) if !ts.is_empty() => Value::Sequence(
                    ts.iter()
                        .map(|t| {
                            let mut tm = Mapping::new();
                            tm.insert(Value::from("min_count"), Value::from(t.min_count));
                            let (r, g, b) = t.color;
                            tm.insert(
                                Value::from("color"),
                                Value::from(format!("#{:02x}{:02x}{:02x}", r, g, b)),
                            );
                            Value::Mapping(tm)
                        })
                        .collect(),
                ),
                _ => Value::Null,
            },
        );
        Value::Mapping(m)
    }
}

pub fn load() -> Settings {
    match std::fs::read_to_string(settings_file()) {
        Ok(s) => match serde_yaml::from_str::<Value>(&s) {
            Ok(v) => Settings::from_value(&v),
            Err(_) => Settings::default(),
        },
        Err(_) => Settings::default(),
    }
}

pub fn save(settings: &Settings) {
    let data = match serde_yaml::to_string(&settings.to_value()) {
        Ok(d) => d,
        Err(_) => return,
    };
    if std::fs::write(settings_tmp(), &data).is_ok() {
        let _ = std::fs::rename(settings_tmp(), settings_file());
    }
}
