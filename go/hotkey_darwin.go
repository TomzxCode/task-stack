//go:build darwin

package main

import (
	"fmt"

	"golang.design/x/hotkey"
)

const hotkeyDefault = "cmd+shift+t"

func modFromString(s string) (hotkey.Modifier, error) {
	switch s {
	case "ctrl":
		return hotkey.ModCtrl, nil
	case "shift":
		return hotkey.ModShift, nil
	case "alt", "option":
		return hotkey.ModOption, nil
	case "cmd", "command":
		return hotkey.ModCmd, nil
	}
	return 0, fmt.Errorf("unknown modifier %q — use ctrl, shift, alt, or cmd", s)
}
