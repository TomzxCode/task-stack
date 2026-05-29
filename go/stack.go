package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// File locations mirror the Python implementation so the two stay
// interchangeable on disk.
func stackFile() string   { return filepath.Join(homeDir(), ".task-stack.yaml") }
func stackTmp() string    { return filepath.Join(homeDir(), ".task-stack.yaml.tmp") }
func historyFile() string { return filepath.Join(homeDir(), ".task-stack.history.yaml") }
func historyTmp() string  { return filepath.Join(homeDir(), ".task-stack.history.yaml.tmp") }

func homeDir() string {
	h, err := os.UserHomeDir()
	if err != nil {
		return "."
	}
	return h
}

// Task is a single entry in the stack. Timestamps are pointers so that an
// absent value can be distinguished from the zero time, matching the optional
// fields in the Python dataclass.
type Task struct {
	Text           string
	CreatedAt      *time.Time
	StartedAt      *time.Time
	LastCurrent    *time.Time
	Duration       float64
	DeletedAt      *time.Time
	Description    string
	ExecutionCount int
}

func (t *Task) IsDeleted() bool { return t.DeletedAt != nil }

// MarkCurrent marks this task as the active one (position 0).
func (t *Task) MarkCurrent(now time.Time) {
	if t.StartedAt == nil {
		n := now
		t.StartedAt = &n
	}
	n := now
	t.LastCurrent = &n
	t.ExecutionCount++
}

// EndCurrentStint folds the live stint since LastCurrent into Duration.
// LastCurrent is left unchanged so it still records when the task was current.
func (t *Task) EndCurrentStint(now time.Time) {
	if t.LastCurrent == nil {
		return
	}
	elapsed := now.Sub(*t.LastCurrent).Seconds()
	if elapsed > 0 {
		t.Duration += elapsed
	}
}

// LiveDuration returns cumulative active seconds plus the live stint since
// LastCurrent. Use this for the task at position 0.
func (t *Task) LiveDuration(now time.Time) float64 {
	total := t.Duration
	if t.LastCurrent != nil {
		elapsed := now.Sub(*t.LastCurrent).Seconds()
		if elapsed > 0 {
			total += elapsed
		}
	}
	return total
}

// ---------------------------------------------------------------------------
// (de)serialization
// ---------------------------------------------------------------------------

func isoFormat(t time.Time) string {
	return t.Format("2006-01-02T15:04:05.000000-07:00")
}

func parseTime(v interface{}) *time.Time {
	// yaml.v3 auto-decodes ISO-8601 timestamps into time.Time when unmarshalling
	// into interface{}; handle that before falling back to string parsing.
	if tm, ok := v.(time.Time); ok {
		return &tm
	}
	s, ok := v.(string)
	if !ok || s == "" {
		return nil
	}
	layouts := []string{
		"2006-01-02T15:04:05.999999999-07:00",
		"2006-01-02T15:04:05-07:00",
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02T15:04:05.999999",
		"2006-01-02T15:04:05",
	}
	for _, l := range layouts {
		if tm, err := time.Parse(l, s); err == nil {
			return &tm
		}
	}
	return nil
}

func scalar(value string) *yaml.Node {
	n := &yaml.Node{Kind: yaml.ScalarNode, Value: value}
	return n
}

// quotedScalar emits a single-quoted string. Timestamps must be quoted so the
// YAML loader (both yaml.v3 and PyYAML) reads them back as strings rather than
// auto-decoding them into a native timestamp type, matching Python's output.
func quotedScalar(value string) *yaml.Node {
	return &yaml.Node{Kind: yaml.ScalarNode, Value: value, Style: yaml.SingleQuotedStyle}
}

// toNode renders the task as an ordered YAML mapping matching the field order
// and conditional inclusion of the Python Task.to_dict.
func (t *Task) toNode() *yaml.Node {
	m := &yaml.Node{Kind: yaml.MappingNode}
	add := func(key string, val *yaml.Node) {
		m.Content = append(m.Content, scalar(key), val)
	}
	add("text", scalar(t.Text))
	if t.CreatedAt != nil {
		add("created_at", quotedScalar(isoFormat(*t.CreatedAt)))
	}
	if t.StartedAt != nil {
		add("started_at", quotedScalar(isoFormat(*t.StartedAt)))
	}
	if t.LastCurrent != nil {
		add("last_current", quotedScalar(isoFormat(*t.LastCurrent)))
	} else {
		nullNode := &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!null", Value: "null"}
		add("last_current", nullNode)
	}
	add("duration", floatScalar(round3(t.Duration)))
	if t.DeletedAt != nil {
		add("deleted_at", quotedScalar(isoFormat(*t.DeletedAt)))
	}
	if t.Description != "" {
		add("description", scalar(t.Description))
	}
	if t.ExecutionCount != 0 {
		ec := &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!int",
			Value: fmt.Sprintf("%d", t.ExecutionCount)}
		add("execution_count", ec)
	}
	return m
}

func round3(v float64) float64 {
	return float64(int64(v*1000+0.5)) / 1000
}

// floatScalar emits a float-looking scalar (always with a decimal point) so the
// loader resolves it as a float without needing an explicit !!float tag,
// matching Python's "0.0" style output.
func floatScalar(v float64) *yaml.Node {
	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.ContainsRune(s, '.') {
		s += ".0"
	}
	return &yaml.Node{Kind: yaml.ScalarNode, Value: s}
}

func taskFromMap(d map[string]interface{}) (Task, bool) {
	text, ok := d["text"].(string)
	if !ok {
		return Task{}, false
	}
	var duration float64
	switch v := d["duration"].(type) {
	case float64:
		duration = v
	case int:
		duration = float64(v)
	case int64:
		duration = float64(v)
	}
	desc, _ := d["description"].(string)
	var execCount int
	switch v := d["execution_count"].(type) {
	case int:
		execCount = v
	case int64:
		execCount = int(v)
	case float64:
		execCount = int(v)
	}
	return Task{
		Text:           text,
		CreatedAt:      parseTime(d["created_at"]),
		StartedAt:      parseTime(d["started_at"]),
		LastCurrent:    parseTime(d["last_current"]),
		Duration:       duration,
		DeletedAt:      parseTime(d["deleted_at"]),
		Description:    desc,
		ExecutionCount: execCount,
	}, true
}

func parseTasks(data interface{}) []Task {
	list, ok := data.([]interface{})
	if !ok {
		return []Task{}
	}
	out := make([]Task, 0, len(list))
	for _, item := range list {
		if m, ok := item.(map[string]interface{}); ok {
			if t, ok := taskFromMap(m); ok {
				out = append(out, t)
			}
		}
	}
	return out
}

func readTasks(path string) []Task {
	raw, err := os.ReadFile(path)
	if err != nil {
		return []Task{}
	}
	var data interface{}
	if err := yaml.Unmarshal(raw, &data); err != nil {
		return []Task{}
	}
	return parseTasks(data)
}

func writeTasks(path, tmp string, tasks []Task) error {
	root := &yaml.Node{Kind: yaml.SequenceNode}
	for i := range tasks {
		root.Content = append(root.Content, tasks[i].toNode())
	}
	out, err := yaml.Marshal(root)
	if err != nil {
		return err
	}
	if err := os.WriteFile(tmp, out, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func saveActive(tasks []Task) error  { return writeTasks(stackFile(), stackTmp(), tasks) }
func saveHistory(tasks []Task) error { return writeTasks(historyFile(), historyTmp(), tasks) }

func loadHistory() []Task { return readTasks(historyFile()) }

// migrateDurations backfills Duration for legacy entries that lack it. Returns
// true if any task was modified.
func migrateDurations(tasks []Task) bool {
	changed := false
	activeIdx := 0
	for i := range tasks {
		t := &tasks[i]
		isRowZeroActive := !t.IsDeleted() && activeIdx == 0
		if !t.IsDeleted() {
			activeIdx++
		}
		if isRowZeroActive {
			continue
		}
		if t.Duration == 0.0 && t.LastCurrent != nil && t.StartedAt != nil &&
			t.LastCurrent.After(*t.StartedAt) {
			t.Duration = t.LastCurrent.Sub(*t.StartedAt).Seconds()
			changed = true
		}
	}
	return changed
}

// loadActive loads active (non-deleted) tasks, handling the two legacy
// migrations: inline deleted tasks (moved to history) and missing durations.
func loadActive() []Task {
	if _, err := os.Stat(stackFile()); err != nil {
		return []Task{}
	}
	all := readTasks(stackFile())
	active := make([]Task, 0, len(all))
	inlineDeleted := make([]Task, 0)
	for _, t := range all {
		if t.IsDeleted() {
			inlineDeleted = append(inlineDeleted, t)
		} else {
			active = append(active, t)
		}
	}

	durationChanged := migrateDurations(active)

	if len(inlineDeleted) > 0 {
		history := append(loadHistory(), inlineDeleted...)
		_ = saveHistory(history)
		_ = saveActive(active)
	} else if durationChanged {
		_ = saveActive(active)
	}
	return active
}

func commit(active []Task) []Task {
	_ = saveActive(active)
	return active
}

// ---------------------------------------------------------------------------
// Public stack operations
// ---------------------------------------------------------------------------

// Load returns the active (non-deleted) task stack.
func Load() []Task { return loadActive() }

// Save replaces the active task stack on disk.
func Save(tasks []Task) { _ = saveActive(tasks) }

// Deleted returns the soft-deleted history, oldest deletions first.
func Deleted() []Task {
	history := loadHistory()
	sort.SliceStable(history, func(i, j int) bool {
		ti, tj := history[i].DeletedAt, history[j].DeletedAt
		if ti == nil {
			return tj != nil
		}
		if tj == nil {
			return false
		}
		return ti.Before(*tj)
	})
	return history
}

func now() time.Time { return time.Now() }

func Push(text string) []Task {
	n := now()
	active := loadActive()
	if len(active) > 0 {
		active[0].EndCurrentStint(n)
	}
	task := Task{Text: trim(text), CreatedAt: tptr(n)}
	task.MarkCurrent(n)
	active = append([]Task{task}, active...)
	return commit(active)
}

// PushNext inserts a new task right after the current one (position 1).
func PushNext(text string) []Task {
	n := now()
	active := loadActive()
	task := Task{Text: trim(text), CreatedAt: tptr(n)}
	if len(active) == 0 {
		task.MarkCurrent(n)
		active = []Task{task}
	} else {
		active = insertAt(active, 1, task)
	}
	return commit(active)
}

// PushLast inserts a new task at the bottom of the active list.
func PushLast(text string) []Task {
	n := now()
	active := loadActive()
	task := Task{Text: trim(text), CreatedAt: tptr(n)}
	if len(active) == 0 {
		task.MarkCurrent(n)
	}
	active = append(active, task)
	return commit(active)
}

func Pop() (*Task, []Task) {
	n := now()
	active := loadActive()
	if len(active) == 0 {
		return nil, []Task{}
	}
	removed := active[0]
	active = active[1:]
	removed.EndCurrentStint(n)
	removed.DeletedAt = tptr(n)
	_ = saveHistory(append(loadHistory(), removed))
	if len(active) > 0 {
		active[0].MarkCurrent(n)
	}
	return &removed, commit(active)
}

func Reorder(fromIdx, toIdx int) []Task {
	n := now()
	active := loadActive()
	if fromIdx == toIdx || fromIdx < 0 || fromIdx >= len(active) ||
		toIdx < 0 || toIdx >= len(active) {
		return active
	}
	headChanges := fromIdx == 0 || toIdx == 0
	if headChanges {
		active[0].EndCurrentStint(n)
	}
	task := active[fromIdx]
	active = append(active[:fromIdx], active[fromIdx+1:]...)
	active = insertAt(active, toIdx, task)
	if headChanges {
		active[0].MarkCurrent(n)
	}
	return commit(active)
}

func Promote(idx int) []Task { return Reorder(idx, 0) }

// ReorderGroup moves a group of tasks together, keeping their relative order.
// It returns the new active list plus a mapping from every old index to its new
// index so callers can translate other indices they track.
func ReorderGroup(fromIndices map[int]bool, anchorIdx, targetIdx int) ([]Task, map[int]int) {
	n := now()
	active := loadActive()
	count := len(active)

	identity := func() map[int]int {
		m := make(map[int]int, count)
		for i := 0; i < count; i++ {
			m[i] = i
		}
		return m
	}

	valid := map[int]bool{}
	for i := range fromIndices {
		if i >= 0 && i < count {
			valid[i] = true
		}
	}
	if len(valid) == 0 || !valid[anchorIdx] || targetIdx < 0 || targetIdx >= count {
		return active, identity()
	}

	blockIndices := sortedKeys(valid)
	block := make([]Task, 0, len(blockIndices))
	anchorOffset := 0
	for off, idx := range blockIndices {
		block = append(block, active[idx])
		if idx == anchorIdx {
			anchorOffset = off
		}
	}

	remainingIndices := make([]int, 0, count-len(valid))
	remaining := make([]Task, 0, count-len(valid))
	for i := 0; i < count; i++ {
		if !valid[i] {
			remainingIndices = append(remainingIndices, i)
			remaining = append(remaining, active[i])
		}
	}

	insertAtPos := targetIdx - anchorOffset
	if insertAtPos < 0 {
		insertAtPos = 0
	}
	if insertAtPos > len(remaining) {
		insertAtPos = len(remaining)
	}

	newActive := make([]Task, 0, count)
	newActive = append(newActive, remaining[:insertAtPos]...)
	newActive = append(newActive, block...)
	newActive = append(newActive, remaining[insertAtPos:]...)

	if tasksEqual(newActive, active) {
		return active, identity()
	}

	newIndex := make(map[int]int, count)
	for off, oldIdx := range blockIndices {
		newIndex[oldIdx] = insertAtPos + off
	}
	for off, oldIdx := range remainingIndices {
		if off < insertAtPos {
			newIndex[oldIdx] = off
		} else {
			newIndex[oldIdx] = off + len(block)
		}
	}

	oldHead := &active[0]
	if !sameTaskPtr(oldHead, &newActive[0]) {
		// Compare by identity of the underlying value: head changed.
		active[0].EndCurrentStint(n)
		newActive[0].MarkCurrent(n)
	}
	return commit(newActive), newIndex
}

// UpdateText updates the text of the active task at idx in place. Empty text is
// rejected.
func UpdateText(idx int, text string) []Task {
	newText := trim(text)
	if newText == "" {
		return loadActive()
	}
	active := loadActive()
	if idx < 0 || idx >= len(active) {
		return active
	}
	active[idx].Text = newText
	return commit(active)
}

// UpdateDescription updates the description of the active task at idx.
func UpdateDescription(idx int, description string) []Task {
	active := loadActive()
	if idx < 0 || idx >= len(active) {
		return active
	}
	active[idx].Description = description
	return commit(active)
}

func Remove(idx int) []Task {
	n := now()
	active := loadActive()
	if idx < 0 || idx >= len(active) {
		return active
	}
	removed := active[idx]
	active = append(active[:idx], active[idx+1:]...)
	if idx == 0 {
		removed.EndCurrentStint(n)
	}
	removed.DeletedAt = tptr(n)
	_ = saveHistory(append(loadHistory(), removed))
	if len(active) > 0 && idx == 0 {
		active[0].MarkCurrent(n)
	}
	return commit(active)
}

// RemoveMany removes multiple tasks atomically, soft-deleting each.
func RemoveMany(indices map[int]bool) []Task {
	n := now()
	active := loadActive()
	valid := make([]int, 0, len(indices))
	for i := range indices {
		if i >= 0 && i < len(active) {
			valid = append(valid, i)
		}
	}
	if len(valid) == 0 {
		return active
	}
	sort.Sort(sort.Reverse(sort.IntSlice(valid)))
	hadCurrentRemoved := indices[0]
	removedTasks := make([]Task, 0, len(valid))
	for _, idx := range valid {
		task := active[idx]
		active = append(active[:idx], active[idx+1:]...)
		if idx == 0 {
			task.EndCurrentStint(n)
		}
		task.DeletedAt = tptr(n)
		removedTasks = append(removedTasks, task)
	}
	_ = saveHistory(append(loadHistory(), removedTasks...))
	if hadCurrentRemoved && len(active) > 0 {
		active[0].MarkCurrent(n)
	}
	return commit(active)
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

func FormatTimestamp(t *time.Time, nowT time.Time) string {
	if t == nil {
		return "—"
	}
	l := t.Local()
	nn := nowT.Local()
	switch {
	case l.Year() != nn.Year():
		return l.Format("2006-01-02 15:04")
	case l.Month() != nn.Month():
		return l.Format("01-02 15:04")
	case l.Day() != nn.Day():
		return l.Format("02 15:04")
	case l.Hour() != nn.Hour():
		return l.Format("15:04")
	default:
		return l.Format("04")
	}
}

// FormatDuration returns a human-readable duration with two units of precision.
func FormatDuration(seconds float64) string {
	total := int64(seconds)
	if total < 0 {
		total = 0
	}
	sec := total % 60
	minutes := (total / 60) % 60
	hours := (total / 3600) % 24
	days := (total / 86400) % 7
	weeks := total / 604800

	if weeks > 0 {
		return fmt.Sprintf("%dw %dd", weeks, days)
	}
	if days > 0 {
		return fmt.Sprintf("%dd %02dh", days, hours)
	}
	if hours > 0 {
		return fmt.Sprintf("%dh %02dm", hours, minutes)
	}
	return fmt.Sprintf("%dm %02ds", minutes, sec)
}

// ---------------------------------------------------------------------------
// small utilities
// ---------------------------------------------------------------------------

func tptr(t time.Time) *time.Time { return &t }

func trim(s string) string {
	// strip leading/trailing ASCII whitespace, matching str.strip semantics for
	// the common cases used here.
	start, end := 0, len(s)
	for start < end && isSpace(s[start]) {
		start++
	}
	for end > start && isSpace(s[end-1]) {
		end--
	}
	return s[start:end]
}

func isSpace(b byte) bool {
	return b == ' ' || b == '\t' || b == '\n' || b == '\r' || b == '\v' || b == '\f'
}

func insertAt(s []Task, idx int, t Task) []Task {
	s = append(s, Task{})
	copy(s[idx+1:], s[idx:])
	s[idx] = t
	return s
}

func sortedKeys(m map[int]bool) []int {
	out := make([]int, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Ints(out)
	return out
}

func tasksEqual(a, b []Task) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].Text != b[i].Text || !sameTime(a[i].CreatedAt, b[i].CreatedAt) {
			return false
		}
	}
	return true
}

func sameTime(a, b *time.Time) bool {
	if a == nil || b == nil {
		return a == b
	}
	return a.Equal(*b)
}

// sameTaskPtr reports whether two tasks refer to the same logical task by
// comparing their stable identity (creation time + text).
func sameTaskPtr(a, b *Task) bool {
	return a.Text == b.Text && sameTime(a.CreatedAt, b.CreatedAt)
}
