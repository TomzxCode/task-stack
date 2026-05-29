package main

import (
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/driver/desktop"
	"fyne.io/fyne/v2/widget"
)

// taskEntry is the single-line input. It rebinds Enter / Shift+Enter / Home /
// End / Escape to the stack actions the Python entry uses, and tracks the Shift
// modifier for that purpose.
type taskEntry struct {
	widget.Entry
	win       *StackWindow
	shiftHeld bool
}

func newTaskEntry(win *StackWindow) *taskEntry {
	e := &taskEntry{win: win}
	e.ExtendBaseWidget(e)
	e.SetPlaceHolder("Type a task and press Enter…")
	return e
}

func (e *taskEntry) KeyDown(ev *fyne.KeyEvent) {
	if ev.Name == desktop.KeyShiftLeft || ev.Name == desktop.KeyShiftRight {
		e.shiftHeld = true
	}
	e.Entry.KeyDown(ev)
}

func (e *taskEntry) KeyUp(ev *fyne.KeyEvent) {
	if ev.Name == desktop.KeyShiftLeft || ev.Name == desktop.KeyShiftRight {
		e.shiftHeld = false
	}
	e.Entry.KeyUp(ev)
}

func (e *taskEntry) TypedKey(ev *fyne.KeyEvent) {
	switch ev.Name {
	case fyne.KeyReturn, fyne.KeyEnter:
		if e.shiftHeld {
			e.win.submitEntry(insertNext)
		} else {
			e.win.submitEntry(insertFirst)
		}
		return
	case fyne.KeyHome:
		e.win.submitEntry(insertFirst)
		return
	case fyne.KeyEnd:
		e.win.submitEntry(insertLast)
		return
	case fyne.KeyEscape:
		e.win.onEntryEscape()
		return
	}
	e.Entry.TypedKey(ev)
}
