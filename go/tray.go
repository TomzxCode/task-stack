package main

import "fyne.io/fyne/v2"

// trayCapable is the subset of the desktop Fyne app that supports a system
// tray. It is implemented by the concrete app on desktop platforms.
type trayCapable interface {
	SetSystemTrayMenu(*fyne.Menu)
	SetSystemTrayIcon(fyne.Resource)
}

// TrayApp owns the system tray icon and menu, mirroring the Python TrayApp.
type TrayApp struct {
	app fyne.App

	hotkeyLabel string
	onOpen      func()
	onPop       func()
	onHelp      func()
	onQuit      func()
}

func NewTrayApp(app fyne.App, hotkeyLabel string, onOpen, onPop, onHelp, onQuit func()) *TrayApp {
	return &TrayApp{
		app:         app,
		hotkeyLabel: hotkeyLabel,
		onOpen:      onOpen,
		onPop:       onPop,
		onHelp:      onHelp,
		onQuit:      onQuit,
	}
}

func (t *TrayApp) Start() {
	tasks := Load()
	t.Update(tasks)
}

func (t *TrayApp) Update(tasks []Task) {
	ta, ok := t.app.(trayCapable)
	if !ok {
		return
	}
	thresholds := LoadSettings().ResolvedIconThresholds()
	ta.SetSystemTrayIcon(MakeIconResource(len(tasks), thresholds))
	ta.SetSystemTrayMenu(t.buildMenu(tasks))
}

func (t *TrayApp) buildMenu(tasks []Task) *fyne.Menu {
	currentLabel := "No tasks"
	if len(tasks) > 0 {
		currentLabel = tasks[0].Text
	}
	openLabel := "Open Stack"
	if t.hotkeyLabel != "" {
		openLabel = "Open Stack (" + t.hotkeyLabel + ")"
	}

	currentItem := fyne.NewMenuItem(currentLabel, nil)
	currentItem.Disabled = true

	popItem := fyne.NewMenuItem("Mark Done (pop)", t.onPop)
	popItem.Disabled = len(tasks) == 0

	helpItem := fyne.NewMenuItem("Keyboard Shortcuts", t.onHelp)
	helpItem.Disabled = t.onHelp == nil

	return fyne.NewMenu("",
		currentItem,
		fyne.NewMenuItemSeparator(),
		fyne.NewMenuItem(openLabel, t.onOpen),
		popItem,
		fyne.NewMenuItemSeparator(),
		helpItem,
		fyne.NewMenuItem("Quit", t.onQuit),
	)
}
