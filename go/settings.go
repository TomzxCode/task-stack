package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

func settingsFile() string { return filepath.Join(homeDir(), ".task-stack.settings.yaml") }
func settingsTmp() string  { return filepath.Join(homeDir(), ".task-stack.settings.yaml.tmp") }

const (
	DefaultHotkey     = "ctrl+shift+t"
	DefaultFontFamily = "TkDefaultFont"
	DefaultFontSize   = 11
)

type WindowGeometry struct {
	Width  int
	Height int
	X      int
	Y      int
}

func windowGeometryFromMap(d map[string]interface{}) *WindowGeometry {
	get := func(k string) (int, bool) {
		switch v := d[k].(type) {
		case int:
			return v, true
		case int64:
			return int(v), true
		case float64:
			return int(v), true
		}
		return 0, false
	}
	w, ok1 := get("width")
	h, ok2 := get("height")
	x, ok3 := get("x")
	y, ok4 := get("y")
	if !ok1 || !ok2 || !ok3 || !ok4 {
		return nil
	}
	return &WindowGeometry{Width: w, Height: h, X: x, Y: y}
}

type RGB struct{ R, G, B uint8 }

type IconThreshold struct {
	MinCount int
	Color    RGB
}

func iconThresholdFromMap(d map[string]interface{}) (IconThreshold, bool) {
	var mc int
	switch v := d["min_count"].(type) {
	case int:
		mc = v
	case int64:
		mc = int(v)
	case float64:
		mc = int(v)
	default:
		return IconThreshold{}, false
	}
	c, ok := d["color"].(string)
	if !ok {
		return IconThreshold{}, false
	}
	rgb, ok := parseHexColor(c)
	if !ok {
		return IconThreshold{}, false
	}
	return IconThreshold{MinCount: mc, Color: rgb}, true
}

func parseHexColor(s string) (RGB, bool) {
	s = strings.TrimPrefix(strings.TrimSpace(s), "#")
	if len(s) != 6 {
		return RGB{}, false
	}
	r, err1 := strconv.ParseUint(s[0:2], 16, 8)
	g, err2 := strconv.ParseUint(s[2:4], 16, 8)
	b, err3 := strconv.ParseUint(s[4:6], 16, 8)
	if err1 != nil || err2 != nil || err3 != nil {
		return RGB{}, false
	}
	return RGB{uint8(r), uint8(g), uint8(b)}, true
}

func (c RGB) hex() string {
	return fmt.Sprintf("#%02x%02x%02x", c.R, c.G, c.B)
}

type Settings struct {
	Window         *WindowGeometry
	Hotkey         string
	FontFamily     string
	FontSize       int
	IconThresholds []IconThreshold // nil means use defaults
}

func defaultSettings() Settings {
	return Settings{
		Window:     nil,
		Hotkey:     DefaultHotkey,
		FontFamily: DefaultFontFamily,
		FontSize:   DefaultFontSize,
	}
}

// ResolvedIconThresholds returns the thresholds sorted by min_count ascending,
// falling back to the defaults when none are configured.
func (s Settings) ResolvedIconThresholds() []IconThreshold {
	thresholds := s.IconThresholds
	if len(thresholds) == 0 {
		thresholds = defaultIconThresholds()
	}
	out := make([]IconThreshold, len(thresholds))
	copy(out, thresholds)
	sort.SliceStable(out, func(i, j int) bool { return out[i].MinCount < out[j].MinCount })
	return out
}

func settingsFromMap(d map[string]interface{}) Settings {
	s := defaultSettings()
	if win, ok := d["window"].(map[string]interface{}); ok {
		s.Window = windowGeometryFromMap(win)
	}
	if hk, ok := d["hotkey"].(string); ok && strings.TrimSpace(hk) != "" {
		s.Hotkey = hk
	}
	if ff, ok := d["font_family"].(string); ok && strings.TrimSpace(ff) != "" {
		s.FontFamily = ff
	}
	switch v := d["font_size"].(type) {
	case int:
		if v >= 6 && v <= 72 {
			s.FontSize = v
		}
	case int64:
		if v >= 6 && v <= 72 {
			s.FontSize = int(v)
		}
	case float64:
		iv := int(v)
		if iv >= 6 && iv <= 72 {
			s.FontSize = iv
		}
	}
	if raw, ok := d["icon_thresholds"].([]interface{}); ok {
		valid := make([]IconThreshold, 0, len(raw))
		for _, item := range raw {
			if m, ok := item.(map[string]interface{}); ok {
				if t, ok := iconThresholdFromMap(m); ok {
					valid = append(valid, t)
				}
			}
		}
		if len(valid) > 0 {
			s.IconThresholds = valid
		}
	}
	return s
}

// LoadSettings reads persisted settings, returning defaults on any error.
func LoadSettings() Settings {
	raw, err := os.ReadFile(settingsFile())
	if err != nil {
		return defaultSettings()
	}
	var data interface{}
	if err := yaml.Unmarshal(raw, &data); err != nil {
		return defaultSettings()
	}
	m, ok := data.(map[string]interface{})
	if !ok {
		return defaultSettings()
	}
	return settingsFromMap(m)
}

func (s Settings) toNode() *yaml.Node {
	root := &yaml.Node{Kind: yaml.MappingNode}
	add := func(key string, val *yaml.Node) {
		root.Content = append(root.Content, scalar(key), val)
	}
	nullNode := func() *yaml.Node {
		return &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!null", Value: "null"}
	}
	intNode := func(v int) *yaml.Node {
		return &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!int", Value: strconv.Itoa(v)}
	}

	if s.Window != nil {
		win := &yaml.Node{Kind: yaml.MappingNode}
		win.Content = append(win.Content, scalar("width"), intNode(s.Window.Width))
		win.Content = append(win.Content, scalar("height"), intNode(s.Window.Height))
		win.Content = append(win.Content, scalar("x"), intNode(s.Window.X))
		win.Content = append(win.Content, scalar("y"), intNode(s.Window.Y))
		add("window", win)
	} else {
		add("window", nullNode())
	}
	add("hotkey", scalar(s.Hotkey))
	add("font_family", scalar(s.FontFamily))
	add("font_size", intNode(s.FontSize))
	if len(s.IconThresholds) > 0 {
		seq := &yaml.Node{Kind: yaml.SequenceNode}
		for _, t := range s.IconThresholds {
			m := &yaml.Node{Kind: yaml.MappingNode}
			m.Content = append(m.Content, scalar("min_count"), intNode(t.MinCount))
			m.Content = append(m.Content, scalar("color"), scalar(t.Color.hex()))
			seq.Content = append(seq.Content, m)
		}
		add("icon_thresholds", seq)
	} else {
		add("icon_thresholds", nullNode())
	}
	return root
}

// SaveSettings writes settings atomically; errors are swallowed (best effort).
func SaveSettings(s Settings) {
	out, err := yaml.Marshal(s.toNode())
	if err != nil {
		return
	}
	if err := os.WriteFile(settingsTmp(), out, 0o644); err != nil {
		return
	}
	_ = os.Rename(settingsTmp(), settingsFile())
}
