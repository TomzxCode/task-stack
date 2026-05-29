package main

import (
	"fmt"
	"strings"

	"golang.design/x/hotkey"
)

// HotkeySpec is a parsed, registrable global hotkey plus a human-readable label.
type HotkeySpec struct {
	Mods   []hotkey.Modifier
	Key    hotkey.Key
	Pretty string
}

// modifierAliases maps user tokens to canonical modifier names. The canonical
// names are resolved to platform Modifier values by modFromString.
var modifierAliases = map[string]string{
	"ctrl":    "ctrl",
	"control": "ctrl",
	"shift":   "shift",
	"alt":     "alt",
	"option":  "alt",
	"opt":     "alt",
	"cmd":     "cmd",
	"command": "cmd",
	"super":   "cmd",
	"win":     "cmd",
	"meta":    "cmd",
}

// namedKeys are the non-character keys the underlying hotkey library can
// register. This is a subset of the Python named keys (the rest are not
// supported by golang.design/x/hotkey).
var namedKeys = map[string]hotkey.Key{
	"space":  hotkey.KeySpace,
	"tab":    hotkey.KeyTab,
	"enter":  hotkey.KeyReturn,
	"return": hotkey.KeyReturn,
	"esc":    hotkey.KeyEscape,
	"escape": hotkey.KeyEscape,
	"delete": hotkey.KeyDelete,
	"up":     hotkey.KeyUp,
	"down":   hotkey.KeyDown,
	"left":   hotkey.KeyLeft,
	"right":  hotkey.KeyRight,
}

var letterKeys = []hotkey.Key{
	hotkey.KeyA, hotkey.KeyB, hotkey.KeyC, hotkey.KeyD, hotkey.KeyE,
	hotkey.KeyF, hotkey.KeyG, hotkey.KeyH, hotkey.KeyI, hotkey.KeyJ,
	hotkey.KeyK, hotkey.KeyL, hotkey.KeyM, hotkey.KeyN, hotkey.KeyO,
	hotkey.KeyP, hotkey.KeyQ, hotkey.KeyR, hotkey.KeyS, hotkey.KeyT,
	hotkey.KeyU, hotkey.KeyV, hotkey.KeyW, hotkey.KeyX, hotkey.KeyY,
	hotkey.KeyZ,
}

var digitKeys = []hotkey.Key{
	hotkey.Key0, hotkey.Key1, hotkey.Key2, hotkey.Key3, hotkey.Key4,
	hotkey.Key5, hotkey.Key6, hotkey.Key7, hotkey.Key8, hotkey.Key9,
}

var fKeys = map[string]hotkey.Key{
	"f1": hotkey.KeyF1, "f2": hotkey.KeyF2, "f3": hotkey.KeyF3, "f4": hotkey.KeyF4,
	"f5": hotkey.KeyF5, "f6": hotkey.KeyF6, "f7": hotkey.KeyF7, "f8": hotkey.KeyF8,
	"f9": hotkey.KeyF9, "f10": hotkey.KeyF10, "f11": hotkey.KeyF11, "f12": hotkey.KeyF12,
	"f13": hotkey.KeyF13, "f14": hotkey.KeyF14, "f15": hotkey.KeyF15, "f16": hotkey.KeyF16,
	"f17": hotkey.KeyF17, "f18": hotkey.KeyF18, "f19": hotkey.KeyF19, "f20": hotkey.KeyF20,
}

func keyFromToken(token string) (hotkey.Key, bool) {
	if k, ok := namedKeys[token]; ok {
		return k, true
	}
	if k, ok := fKeys[token]; ok {
		return k, true
	}
	if len(token) == 1 {
		c := token[0]
		if c >= 'a' && c <= 'z' {
			return letterKeys[c-'a'], true
		}
		if c >= '0' && c <= '9' {
			return digitKeys[c-'0'], true
		}
	}
	return 0, false
}

func titleCase(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}

// ParseHotkey parses a "+"-separated spec like "ctrl+shift+t" into a HotkeySpec.
func ParseHotkey(spec string) (HotkeySpec, error) {
	if strings.TrimSpace(spec) == "" {
		return HotkeySpec{}, fmt.Errorf("empty hotkey spec")
	}
	rawParts := strings.Split(spec, "+")
	parts := make([]string, 0, len(rawParts))
	for _, p := range rawParts {
		p = strings.ToLower(strings.TrimSpace(p))
		if p != "" {
			parts = append(parts, p)
		}
	}
	if len(parts) == 0 {
		return HotkeySpec{}, fmt.Errorf("could not parse hotkey: %q", spec)
	}

	var mods []hotkey.Modifier
	var keyToken string
	var prettyParts []string
	seenMods := map[string]bool{}

	for _, token := range parts {
		if canonical, ok := modifierAliases[token]; ok {
			if seenMods[canonical] {
				continue
			}
			seenMods[canonical] = true
			m, err := modFromString(canonical)
			if err != nil {
				return HotkeySpec{}, err
			}
			mods = append(mods, m)
			prettyParts = append(prettyParts, titleCase(canonical))
			continue
		}
		if keyToken != "" {
			return HotkeySpec{}, fmt.Errorf(
				"hotkey %q has more than one non-modifier key (saw %q and %q)",
				spec, keyToken, token)
		}
		keyToken = token
		if len(token) == 1 {
			prettyParts = append(prettyParts, token)
		} else {
			prettyParts = append(prettyParts, titleCase(token))
		}
	}

	if keyToken == "" {
		return HotkeySpec{}, fmt.Errorf("hotkey %q is missing a non-modifier key", spec)
	}
	key, ok := keyFromToken(keyToken)
	if !ok {
		return HotkeySpec{}, fmt.Errorf("unrecognized key token %q in hotkey %q", keyToken, spec)
	}

	return HotkeySpec{
		Mods:   mods,
		Key:    key,
		Pretty: strings.Join(prettyParts, "+"),
	}, nil
}

// ParseHotkeyOrDefault returns the parsed spec, falling back to def on error.
func ParseHotkeyOrDefault(spec, def string) HotkeySpec {
	s, err := ParseHotkey(spec)
	if err != nil {
		s, _ = ParseHotkey(def)
	}
	return s
}
