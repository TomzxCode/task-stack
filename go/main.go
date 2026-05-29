package main

import (
	"os"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
)

// AppCoordinator wires the tray, hotkey listener, and window together. Window
// mutations are marshalled onto Fyne's main goroutine via fyne.Do so background
// goroutines (the hotkey listener) never touch the UI directly.
type AppCoordinator struct {
	app    fyne.App
	window *StackWindow
	tray   *TrayApp
}

func (c *AppCoordinator) RequestShow() {
	fyne.Do(func() { c.window.Show() })
}

func (c *AppCoordinator) RequestToggle() {
	fyne.Do(func() {
		if c.window.IsVisible() {
			c.window.Hide()
		} else {
			c.window.Show()
		}
	})
}

func (c *AppCoordinator) RequestHelp() {
	fyne.Do(func() { c.window.ShowHelp() })
}

func (c *AppCoordinator) RequestQuit() {
	fyne.Do(func() { c.app.Quit() })
}

// NotifyStackChanged reloads the stack from disk and refreshes the tray and
// window. Safe to call from any goroutine.
func (c *AppCoordinator) NotifyStackChanged() {
	fyne.Do(func() {
		tasks := Load()
		if c.tray != nil {
			c.tray.Update(tasks)
		}
		c.window.Refresh()
	})
}

func main() {
	fyneApp := app.NewWithID("com.taskstack.app")

	coordinator := &AppCoordinator{app: fyneApp}

	window := NewStackWindow(fyneApp, func() {
		// Window edited the stack: refresh the tray to match.
		if coordinator.tray != nil {
			coordinator.tray.Update(Load())
		}
	})
	coordinator.window = window

	settings := LoadSettings()
	spec := ParseHotkeyOrDefault(settings.Hotkey, DefaultHotkey)
	if _, err := ParseHotkey(settings.Hotkey); err != nil {
		os.Stderr.WriteString("task-stack: invalid hotkey " + settings.Hotkey +
			"; falling back to " + DefaultHotkey + "\n")
	}

	tray := NewTrayApp(
		fyneApp,
		spec.Pretty,
		coordinator.RequestShow,
		func() { // pop from tray
			Pop()
			coordinator.NotifyStackChanged()
		},
		coordinator.RequestHelp,
		coordinator.RequestQuit,
	)
	coordinator.tray = tray
	tray.Start()

	hotkey := NewHotkeyListener(coordinator.RequestToggle)
	hotkey.Apply(spec)
	defer hotkey.Stop()

	fyneApp.Run()
}
