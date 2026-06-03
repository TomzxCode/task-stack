//! YAML-backed task store with soft deletes.
//!
//! Port of the original `task_stack.stack` Python module. Active tasks live in
//! `~/.task-stack.yaml`; soft-deleted tasks are appended to
//! `~/.task-stack.history.yaml`. Active tasks are held in memory as the source
//! of truth and persisted atomically on every mutation.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use chrono::{DateTime, Local, TimeZone};
use serde::Serialize;
use serde_yaml::{Mapping, Value};

fn home() -> PathBuf {
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("."))
}

fn stack_file() -> PathBuf {
    home().join(".task-stack.yaml")
}

fn stack_tmp() -> PathBuf {
    home().join(".task-stack.yaml.tmp")
}

fn history_file() -> PathBuf {
    home().join(".task-stack.history.yaml")
}

fn history_tmp() -> PathBuf {
    home().join(".task-stack.history.yaml.tmp")
}

#[derive(Clone, Debug)]
pub struct Task {
    pub text: String,
    pub created_at: Option<DateTime<Local>>,
    pub started_at: Option<DateTime<Local>>,
    pub last_current: Option<DateTime<Local>>,
    pub duration: f64,
    pub deleted_at: Option<DateTime<Local>>,
    pub description: String,
    pub execution_count: i64,
}

impl Task {
    fn new(text: String, created_at: Option<DateTime<Local>>) -> Self {
        Task {
            text,
            created_at,
            started_at: None,
            last_current: None,
            duration: 0.0,
            deleted_at: None,
            description: String::new(),
            execution_count: 0,
        }
    }

    pub fn is_deleted(&self) -> bool {
        self.deleted_at.is_some()
    }

    /// Mark this task as the active one (position 0).
    fn mark_current(&mut self, now: DateTime<Local>) {
        if self.started_at.is_none() {
            self.started_at = Some(now);
        }
        self.last_current = Some(now);
        self.execution_count += 1;
    }

    /// Accumulate the live stint since `last_current` into `duration`.
    fn end_current_stint(&mut self, now: DateTime<Local>) {
        if let Some(lc) = self.last_current {
            let elapsed = (now - lc).num_milliseconds() as f64 / 1000.0;
            if elapsed > 0.0 {
                self.duration += elapsed;
            }
        }
    }

    /// Cumulative active seconds plus the live stint since `last_current`.
    ///
    /// The frontend recomputes this each second from the raw epoch values, so
    /// this Rust port is retained for parity but not currently called.
    #[allow(dead_code)]
    pub fn live_duration(&self, now: DateTime<Local>) -> f64 {
        let mut total = self.duration;
        if let Some(lc) = self.last_current {
            let elapsed = (now - lc).num_milliseconds() as f64 / 1000.0;
            if elapsed > 0.0 {
                total += elapsed;
            }
        }
        total
    }

    fn to_value(&self) -> Value {
        let mut m = Mapping::new();
        m.insert(Value::from("text"), Value::from(self.text.clone()));
        if let Some(dt) = self.created_at {
            m.insert(Value::from("created_at"), Value::from(dt.to_rfc3339()));
        }
        if let Some(dt) = self.started_at {
            m.insert(Value::from("started_at"), Value::from(dt.to_rfc3339()));
        }
        m.insert(
            Value::from("last_current"),
            match self.last_current {
                Some(dt) => Value::from(dt.to_rfc3339()),
                None => Value::Null,
            },
        );
        // round to 3 decimals to mirror the Python writer
        let dur = (self.duration * 1000.0).round() / 1000.0;
        m.insert(Value::from("duration"), Value::from(dur));
        if let Some(dt) = self.deleted_at {
            m.insert(Value::from("deleted_at"), Value::from(dt.to_rfc3339()));
        }
        if !self.description.is_empty() {
            m.insert(Value::from("description"), Value::from(self.description.clone()));
        }
        if self.execution_count != 0 {
            m.insert(Value::from("execution_count"), Value::from(self.execution_count));
        }
        Value::Mapping(m)
    }

    fn from_value(v: &Value) -> Option<Task> {
        let m = v.as_mapping()?;
        let text = m.get(Value::from("text"))?.as_str()?.to_string();
        let parse = |key: &str| -> Option<DateTime<Local>> {
            m.get(Value::from(key))
                .and_then(|x| x.as_str())
                .filter(|s| !s.is_empty())
                .and_then(parse_dt)
        };
        let duration = m
            .get(Value::from("duration"))
            .and_then(|x| x.as_f64().or_else(|| x.as_i64().map(|n| n as f64)))
            .unwrap_or(0.0);
        let description = m
            .get(Value::from("description"))
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string();
        let execution_count = m
            .get(Value::from("execution_count"))
            .and_then(|x| x.as_i64())
            .unwrap_or(0);
        Some(Task {
            text,
            created_at: parse("created_at"),
            started_at: parse("started_at"),
            last_current: parse("last_current"),
            duration,
            deleted_at: parse("deleted_at"),
            description,
            execution_count,
        })
    }
}

fn parse_dt(s: &str) -> Option<DateTime<Local>> {
    DateTime::parse_from_rfc3339(s)
        .ok()
        .map(|dt| dt.with_timezone(&Local))
        // also accept naive datetimes (assume local) as a fallback
        .or_else(|| {
            chrono::NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S%.f")
                .ok()
                .and_then(|n| Local.from_local_datetime(&n).single())
        })
}

/// View model handed to the frontend; epochs are seconds since the Unix epoch.
#[derive(Serialize, Clone)]
pub struct TaskView {
    pub text: String,
    pub description: String,
    pub is_current: bool,
    pub started_epoch: Option<f64>,
    pub last_current_epoch: Option<f64>,
    pub duration_seconds: f64,
    pub execution_count: i64,
}

fn epoch(dt: Option<DateTime<Local>>) -> Option<f64> {
    dt.map(|d| d.timestamp_millis() as f64 / 1000.0)
}

pub fn to_views(tasks: &[Task]) -> Vec<TaskView> {
    tasks
        .iter()
        .enumerate()
        .map(|(i, t)| TaskView {
            text: t.text.clone(),
            description: t.description.clone(),
            is_current: i == 0,
            started_epoch: epoch(t.started_at),
            last_current_epoch: epoch(t.last_current),
            duration_seconds: t.duration,
            execution_count: t.execution_count,
        })
        .collect()
}

fn dump(tasks: &[Task]) -> String {
    let seq: Vec<Value> = tasks.iter().map(|t| t.to_value()).collect();
    serde_yaml::to_string(&Value::Sequence(seq)).unwrap_or_default()
}

fn parse_tasks(data: &Value) -> Vec<Task> {
    match data.as_sequence() {
        Some(seq) => seq.iter().filter_map(Task::from_value).collect(),
        None => Vec::new(),
    }
}

fn load_history() -> Vec<Task> {
    match std::fs::read_to_string(history_file()) {
        Ok(s) => serde_yaml::from_str::<Value>(&s)
            .map(|v| parse_tasks(&v))
            .unwrap_or_default(),
        Err(_) => Vec::new(),
    }
}

fn save_history(tasks: &[Task]) {
    let data = dump(tasks);
    if std::fs::write(history_tmp(), &data).is_ok() {
        let _ = std::fs::rename(history_tmp(), history_file());
    }
}

fn save_active(tasks: &[Task]) {
    let data = dump(tasks);
    if std::fs::write(stack_tmp(), &data).is_ok() {
        let _ = std::fs::rename(stack_tmp(), stack_file());
    }
}

/// Backfill `duration` for legacy entries that lack it. Returns true if changed.
fn migrate_durations(tasks: &mut [Task]) -> bool {
    let mut changed = false;
    let mut active_idx = 0usize;
    for t in tasks.iter_mut() {
        let is_row_zero_active = !t.is_deleted() && active_idx == 0;
        if !t.is_deleted() {
            active_idx += 1;
        }
        if is_row_zero_active {
            continue;
        }
        if t.duration == 0.0 {
            if let (Some(lc), Some(st)) = (t.last_current, t.started_at) {
                if lc > st {
                    t.duration = (lc - st).num_milliseconds() as f64 / 1000.0;
                    changed = true;
                }
            }
        }
    }
    changed
}

/// Load active (non-deleted) tasks, performing legacy migrations on first load.
pub fn load_active() -> Vec<Task> {
    let raw = match std::fs::read_to_string(stack_file()) {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };
    let data = match serde_yaml::from_str::<Value>(&raw) {
        Ok(v) => v,
        Err(_) => return Vec::new(),
    };
    let all = parse_tasks(&data);
    let mut active: Vec<Task> = all.iter().filter(|t| !t.is_deleted()).cloned().collect();
    let inline_deleted: Vec<Task> = all.iter().filter(|t| t.is_deleted()).cloned().collect();

    let duration_changed = migrate_durations(&mut active);

    if !inline_deleted.is_empty() {
        let mut history = load_history();
        history.extend(inline_deleted);
        save_history(&history);
        save_active(&active);
    } else if duration_changed {
        save_active(&active);
    }

    active
}

/// In-memory store of the active task stack.
pub struct Store {
    pub active: Vec<Task>,
}

impl Store {
    pub fn load() -> Self {
        Store { active: load_active() }
    }

    fn commit(&mut self) {
        save_active(&self.active);
    }

    pub fn views(&self) -> Vec<TaskView> {
        to_views(&self.active)
    }

    pub fn current_text(&self) -> Option<String> {
        self.active.first().map(|t| t.text.clone())
    }

    pub fn count(&self) -> usize {
        self.active.len()
    }

    pub fn push(&mut self, text: &str, now: DateTime<Local>) {
        if let Some(first) = self.active.first_mut() {
            first.end_current_stint(now);
        }
        let mut task = Task::new(text.trim().to_string(), Some(now));
        task.mark_current(now);
        self.active.insert(0, task);
        self.commit();
    }

    pub fn push_next(&mut self, text: &str, now: DateTime<Local>) {
        let mut task = Task::new(text.trim().to_string(), Some(now));
        if self.active.is_empty() {
            task.mark_current(now);
            self.active.insert(0, task);
        } else {
            self.active.insert(1, task);
        }
        self.commit();
    }

    pub fn push_last(&mut self, text: &str, now: DateTime<Local>) {
        let mut task = Task::new(text.trim().to_string(), Some(now));
        if self.active.is_empty() {
            task.mark_current(now);
        }
        self.active.push(task);
        self.commit();
    }

    pub fn pop(&mut self, now: DateTime<Local>) {
        if self.active.is_empty() {
            return;
        }
        let mut removed = self.active.remove(0);
        removed.end_current_stint(now);
        removed.deleted_at = Some(now);
        let mut history = load_history();
        history.push(removed);
        save_history(&history);
        if let Some(first) = self.active.first_mut() {
            first.mark_current(now);
        }
        self.commit();
    }

    pub fn reorder(&mut self, from_idx: usize, to_idx: usize, now: DateTime<Local>) {
        let n = self.active.len();
        if from_idx == to_idx || from_idx >= n || to_idx >= n {
            return;
        }
        let head_changes = from_idx == 0 || to_idx == 0;
        if head_changes {
            self.active[0].end_current_stint(now);
        }
        let task = self.active.remove(from_idx);
        self.active.insert(to_idx, task);
        if head_changes {
            self.active[0].mark_current(now);
        }
        self.commit();
    }

    pub fn promote(&mut self, idx: usize, now: DateTime<Local>) {
        self.reorder(idx, 0, now);
    }

    /// Move a group of tasks together, keeping their relative order. Returns a
    /// mapping from every old active index to its new index.
    pub fn reorder_group(
        &mut self,
        from_indices: &HashSet<usize>,
        anchor_idx: usize,
        target_idx: usize,
        now: DateTime<Local>,
    ) -> HashMap<usize, usize> {
        let n = self.active.len();
        let identity = || -> HashMap<usize, usize> { (0..n).map(|i| (i, i)).collect() };

        let valid: HashSet<usize> = from_indices.iter().cloned().filter(|&i| i < n).collect();
        if valid.is_empty() || !valid.contains(&anchor_idx) || target_idx >= n {
            return identity();
        }

        let mut block_indices: Vec<usize> = valid.iter().cloned().collect();
        block_indices.sort_unstable();
        let anchor_offset = block_indices.iter().position(|&i| i == anchor_idx).unwrap();

        let remaining_indices: Vec<usize> = (0..n).filter(|i| !valid.contains(i)).collect();

        let insert_at = (target_idx as isize - anchor_offset as isize)
            .max(0)
            .min(remaining_indices.len() as isize) as usize;

        // Build new ordering by task identity (index references into old vec).
        let mut new_order: Vec<usize> = Vec::with_capacity(n);
        new_order.extend_from_slice(&remaining_indices[..insert_at]);
        new_order.extend_from_slice(&block_indices);
        new_order.extend_from_slice(&remaining_indices[insert_at..]);

        // No-op?
        if new_order.iter().cloned().eq(0..n) {
            return identity();
        }

        let mut index_map: HashMap<usize, usize> = HashMap::new();
        for (offset, &old_idx) in block_indices.iter().enumerate() {
            index_map.insert(old_idx, insert_at + offset);
        }
        for (offset, &old_idx) in remaining_indices.iter().enumerate() {
            if offset < insert_at {
                index_map.insert(old_idx, offset);
            } else {
                index_map.insert(old_idx, offset + block_indices.len());
            }
        }

        let old_head_changes = new_order[0] != 0;

        // Rebuild active in the new order.
        let mut new_active: Vec<Option<Task>> = self.active.drain(..).map(Some).collect();
        let rebuilt: Vec<Task> = new_order
            .iter()
            .map(|&old_idx| new_active[old_idx].take().unwrap())
            .collect();
        self.active = rebuilt;

        if old_head_changes {
            // The task that was at old index 0 is no longer the head.
            // End its stint, mark the new head current.
            if let Some(new_pos_of_old_head) = index_map.get(&0) {
                self.active[*new_pos_of_old_head].end_current_stint(now);
            }
            self.active[0].mark_current(now);
        }

        self.commit();
        index_map
    }

    pub fn update_text(&mut self, idx: usize, text: &str) {
        let new_text = text.trim();
        if new_text.is_empty() || idx >= self.active.len() {
            return;
        }
        self.active[idx].text = new_text.to_string();
        self.commit();
    }

    pub fn update_description(&mut self, idx: usize, description: &str) {
        if idx >= self.active.len() {
            return;
        }
        self.active[idx].description = description.to_string();
        self.commit();
    }

    pub fn remove(&mut self, idx: usize, now: DateTime<Local>) {
        if idx >= self.active.len() {
            return;
        }
        let mut removed = self.active.remove(idx);
        if idx == 0 {
            removed.end_current_stint(now);
        }
        removed.deleted_at = Some(now);
        let mut history = load_history();
        history.push(removed);
        save_history(&history);
        if idx == 0 {
            if let Some(first) = self.active.first_mut() {
                first.mark_current(now);
            }
        }
        self.commit();
    }

    pub fn remove_many(&mut self, indices: &HashSet<usize>, now: DateTime<Local>) {
        let n = self.active.len();
        let mut valid: Vec<usize> = indices.iter().cloned().filter(|&i| i < n).collect();
        valid.sort_unstable();
        valid.reverse();
        if valid.is_empty() {
            return;
        }
        let had_current_removed = indices.contains(&0);
        let mut removed_tasks: Vec<Task> = Vec::new();
        for idx in valid {
            let mut task = self.active.remove(idx);
            if idx == 0 {
                task.end_current_stint(now);
            }
            task.deleted_at = Some(now);
            removed_tasks.push(task);
        }
        let mut history = load_history();
        history.extend(removed_tasks);
        save_history(&history);
        if had_current_removed {
            if let Some(first) = self.active.first_mut() {
                first.mark_current(now);
            }
        }
        self.commit();
    }
}
