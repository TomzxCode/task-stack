//go:build !darwin && !windows

package main

import (
	"fmt"

	"golang.design/x/hotkey"
)

func modFromString(canonical string) (hotkey.Modifier, error) {
	switch canonical {
	case "ctrl":
		return hotkey.ModCtrl, nil
	case "shift":
		return hotkey.ModShift, nil
	case "alt":
		return hotkey.Mod1, nil
	case "cmd":
		return hotkey.Mod4, nil
	}
	return 0, fmt.Errorf("unknown modifier %q", canonical)
}
