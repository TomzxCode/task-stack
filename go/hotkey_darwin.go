//go:build darwin

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
		return hotkey.ModOption, nil
	case "cmd":
		return hotkey.ModCmd, nil
	}
	return 0, fmt.Errorf("unknown modifier %q", canonical)
}
