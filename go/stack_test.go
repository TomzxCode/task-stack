package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// useTempHome points the on-disk files at a temp dir for the duration of a test.
func useTempHome(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("HOME", dir)
	// On some platforms UserHomeDir uses other vars; set them too.
	t.Setenv("USERPROFILE", dir)
}

func TestPushPopRoundTrip(t *testing.T) {
	useTempHome(t)

	tasks := Push("first")
	if len(tasks) != 1 || tasks[0].Text != "first" {
		t.Fatalf("push: got %+v", tasks)
	}
	if tasks[0].ExecutionCount != 1 {
		t.Fatalf("expected execution_count 1, got %d", tasks[0].ExecutionCount)
	}
	if tasks[0].StartedAt == nil || tasks[0].LastCurrent == nil {
		t.Fatalf("expected started_at/last_current set")
	}

	tasks = Push("second")
	if len(tasks) != 2 || tasks[0].Text != "second" {
		t.Fatalf("push second: %+v", tasks)
	}

	// Reload from disk; data should persist.
	reloaded := Load()
	if len(reloaded) != 2 || reloaded[0].Text != "second" {
		t.Fatalf("reload: %+v", reloaded)
	}

	removed, after := Pop()
	if removed == nil || removed.Text != "second" {
		t.Fatalf("pop: %+v", removed)
	}
	if len(after) != 1 || after[0].Text != "first" {
		t.Fatalf("after pop: %+v", after)
	}
	if after[0].ExecutionCount != 2 {
		t.Fatalf("promoted task should re-mark current; exec=%d", after[0].ExecutionCount)
	}

	del := Deleted()
	if len(del) != 1 || del[0].Text != "second" || del[0].DeletedAt == nil {
		t.Fatalf("history: %+v", del)
	}
}

func TestPushNextAndLast(t *testing.T) {
	useTempHome(t)
	Push("a")
	Push("b") // b is current at 0, a at 1
	tasks := PushNext("c")
	if tasks[1].Text != "c" {
		t.Fatalf("push_next should be at index 1: %+v", tasks)
	}
	tasks = PushLast("d")
	if tasks[len(tasks)-1].Text != "d" {
		t.Fatalf("push_last should be at end: %+v", tasks)
	}
}

func TestReorderGroup(t *testing.T) {
	useTempHome(t)
	Push("a")
	Push("b")
	Push("c") // order: c,b,a
	// Move the block {c,b} (indices 0,1) so anchor c lands at index 1.
	tasks, idxMap := ReorderGroup(map[int]bool{0: true, 1: true}, 0, 1)
	if len(tasks) != 3 {
		t.Fatalf("expected 3 tasks: %+v", tasks)
	}
	// a should now be first.
	if tasks[0].Text != "a" {
		t.Fatalf("expected a first after group move: %+v", tasks)
	}
	if idxMap[0] != 1 {
		t.Fatalf("index map should track moved anchor: %v", idxMap)
	}
}

func TestRemoveMany(t *testing.T) {
	useTempHome(t)
	Push("a")
	Push("b")
	Push("c")
	Push("d") // d,c,b,a
	tasks := RemoveMany(map[int]bool{0: true, 2: true})
	if len(tasks) != 2 {
		t.Fatalf("expected 2 left: %+v", tasks)
	}
	if tasks[0].Text != "c" || tasks[1].Text != "a" {
		t.Fatalf("unexpected survivors: %+v", tasks)
	}
	if len(Deleted()) != 2 {
		t.Fatalf("expected 2 deleted")
	}
}

func TestYAMLCompatibility(t *testing.T) {
	useTempHome(t)
	Push("hello world")
	raw, err := os.ReadFile(filepath.Join(os.Getenv("HOME"), ".task-stack.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	for _, want := range []string{"text:", "last_current:", "duration:"} {
		if !contains(s, want) {
			t.Fatalf("yaml missing %q:\n%s", want, s)
		}
	}
}

func TestFormatDuration(t *testing.T) {
	cases := map[float64]string{
		45:               "0m 45s",
		125:              "2m 05s",
		7325:             "2h 02m",
		90000:            "1d 01h",
		60 * 60 * 24 * 8: "1w 1d",
	}
	for secs, want := range cases {
		if got := FormatDuration(secs); got != want {
			t.Errorf("FormatDuration(%v) = %q, want %q", secs, got, want)
		}
	}
}

func TestFormatTimestamp(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.Local)
	sameHour := time.Date(2026, 5, 29, 12, 30, 0, 0, time.Local)
	if got := FormatTimestamp(&sameHour, now); got != "30" {
		t.Errorf("same hour: got %q", got)
	}
	otherDay := time.Date(2026, 5, 28, 9, 15, 0, 0, time.Local)
	if got := FormatTimestamp(&otherDay, now); got != "28 09:15" {
		t.Errorf("other day: got %q", got)
	}
	if got := FormatTimestamp(nil, now); got != "—" {
		t.Errorf("nil: got %q", got)
	}
}

func TestHotkeyParse(t *testing.T) {
	spec, err := ParseHotkey("ctrl+shift+t")
	if err != nil {
		t.Fatal(err)
	}
	if spec.Pretty != "Ctrl+Shift+t" {
		t.Errorf("pretty: %q", spec.Pretty)
	}
	if len(spec.Mods) != 2 {
		t.Errorf("mods: %v", spec.Mods)
	}
	if _, err := ParseHotkey("justakey"); err == nil {
		t.Error("expected error for modifier-less spec without recognizing 'justakey' as key")
	}
	if _, err := ParseHotkey(""); err == nil {
		t.Error("expected error for empty spec")
	}
}

func TestSettingsRoundTrip(t *testing.T) {
	useTempHome(t)
	s := defaultSettings()
	s.Hotkey = "alt+f5"
	s.FontSize = 14
	s.Window = &WindowGeometry{Width: 500, Height: 300, X: 10, Y: 20}
	s.IconThresholds = []IconThreshold{{MinCount: 3, Color: RGB{1, 2, 3}}}
	SaveSettings(s)

	got := LoadSettings()
	if got.Hotkey != "alt+f5" || got.FontSize != 14 {
		t.Fatalf("settings: %+v", got)
	}
	if got.Window == nil || got.Window.Width != 500 || got.Window.X != 10 {
		t.Fatalf("window geom: %+v", got.Window)
	}
	if len(got.IconThresholds) != 1 || got.IconThresholds[0].Color != (RGB{1, 2, 3}) {
		t.Fatalf("thresholds: %+v", got.IconThresholds)
	}
}

func TestIconColorThresholds(t *testing.T) {
	th := defaultIconThresholds()
	if iconColor(0, th) != bgEmpty {
		t.Error("count 0 should be grey")
	}
	if c := iconColor(1, th); c != (RGB{70, 130, 180}) {
		t.Errorf("count 1 should be blue, got %v", c)
	}
	if c := iconColor(12, th); c != (RGB{200, 50, 50}) {
		t.Errorf("count 12 should be red, got %v", c)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
