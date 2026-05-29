package main

import "image/color"

// Theme mirrors the light/dark palettes from the Python window module.
type Theme struct {
	Bg         color.Color
	BgFrame    color.Color
	SelectedBg color.Color
	Fg         color.Color
	FgDim      color.Color
	FgMuted    color.Color
	EntryBg    color.Color
	EntryFg    color.Color
	DragHandle color.Color
	BtnBg      color.Color
	BtnFg      color.Color
	LinkFg     color.Color
}

func hexColor(s string) color.Color {
	rgb, ok := parseHexColor(s)
	if !ok {
		return color.Black
	}
	return color.NRGBA{R: rgb.R, G: rgb.G, B: rgb.B, A: 255}
}

var lightTheme = Theme{
	Bg:         hexColor("#ffffff"),
	BgFrame:    hexColor("#f0f0f0"),
	SelectedBg: hexColor("#d0e4ff"),
	Fg:         hexColor("#111111"),
	FgDim:      hexColor("#444444"),
	FgMuted:    hexColor("#888888"),
	EntryBg:    hexColor("#ffffff"),
	EntryFg:    hexColor("#111111"),
	DragHandle: hexColor("#aaaaaa"),
	BtnBg:      hexColor("#4a90e2"),
	BtnFg:      hexColor("#ffffff"),
	LinkFg:     hexColor("#1a6ed8"),
}

var darkTheme = Theme{
	Bg:         hexColor("#1e1e1e"),
	BgFrame:    hexColor("#2d2d2d"),
	SelectedBg: hexColor("#1a3a5c"),
	Fg:         hexColor("#e0e0e0"),
	FgDim:      hexColor("#b0b0b0"),
	FgMuted:    hexColor("#707070"),
	EntryBg:    hexColor("#3c3c3c"),
	EntryFg:    hexColor("#e0e0e0"),
	DragHandle: hexColor("#666666"),
	BtnBg:      hexColor("#2a6099"),
	BtnFg:      hexColor("#e0e0e0"),
	LinkFg:     hexColor("#6ea8fe"),
}
