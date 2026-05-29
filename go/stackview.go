package main

import (
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/driver/desktop"
	"fyne.io/fyne/v2/widget"
)

// stackView is the custom widget that draws the task rows and handles mouse and
// keyboard input, replicating the canvas-based UI of the Python window.
type stackView struct {
	widget.BaseWidget

	win           *StackWindow
	objects       []fyne.CanvasObject
	contentHeight float32
	width         float32

	shiftHeld bool

	pressRow   int
	pressShift bool
	dragMoved  bool
	dragY      float32
}

func newStackView(win *StackWindow) *stackView {
	sv := &stackView{win: win}
	sv.ExtendBaseWidget(sv)
	return sv
}

// setObjects replaces the drawn objects and the reported content height.
func (sv *stackView) setObjects(objs []fyne.CanvasObject, height float32) {
	sv.objects = objs
	sv.contentHeight = height
	sv.Refresh()
}

func (sv *stackView) CreateRenderer() fyne.WidgetRenderer {
	return &stackRenderer{sv: sv}
}

// ---- Focusable ----

func (sv *stackView) FocusGained() {}
func (sv *stackView) FocusLost()   {}

func (sv *stackView) TypedRune(r rune) { sv.win.onCanvasRune(r) }

func (sv *stackView) TypedKey(ev *fyne.KeyEvent) { sv.win.onCanvasKey(ev, sv.shiftHeld) }

// ---- desktop.Keyable (modifier tracking) ----

func (sv *stackView) KeyDown(ev *fyne.KeyEvent) {
	if ev.Name == desktop.KeyShiftLeft || ev.Name == desktop.KeyShiftRight {
		sv.shiftHeld = true
	}
}

func (sv *stackView) KeyUp(ev *fyne.KeyEvent) {
	if ev.Name == desktop.KeyShiftLeft || ev.Name == desktop.KeyShiftRight {
		sv.shiftHeld = false
	}
}

// ---- desktop.Mouseable ----

func (sv *stackView) MouseDown(ev *desktop.MouseEvent) {
	sv.win.focusCanvas()
	sv.pressRow = sv.win.rowAt(ev.Position.Y)
	sv.pressShift = ev.Modifier&fyne.KeyModifierShift != 0
	sv.dragMoved = false
	sv.dragY = ev.Position.Y
	sv.win.dragPress(sv.pressRow, ev.Position.Y)
}

func (sv *stackView) MouseUp(ev *desktop.MouseEvent) {}

// ---- fyne.Tappable (click without drag) ----

func (sv *stackView) Tapped(ev *fyne.PointEvent) {
	if sv.dragMoved {
		return
	}
	row := sv.win.rowAt(ev.Position.Y)
	sv.win.clickSelect(row, sv.pressShift)
}

// ---- fyne.Draggable ----

func (sv *stackView) Dragged(ev *fyne.DragEvent) {
	sv.dragMoved = true
	sv.dragY = ev.Position.Y
	sv.win.dragMotion(ev.Position.Y)
}

func (sv *stackView) DragEnd() {
	sv.win.dragRelease()
	sv.dragMoved = false
}

// stackRenderer renders the absolutely-positioned objects produced by redraw.
type stackRenderer struct {
	sv *stackView
}

func (r *stackRenderer) Destroy() {}

func (r *stackRenderer) Layout(size fyne.Size) {
	if size.Width != r.sv.width {
		r.sv.width = size.Width
		r.sv.win.redraw()
	}
}

func (r *stackRenderer) MinSize() fyne.Size {
	h := r.sv.contentHeight
	if h < rowHeight {
		h = rowHeight
	}
	return fyne.NewSize(200, h)
}

func (r *stackRenderer) Objects() []fyne.CanvasObject { return r.sv.objects }

func (r *stackRenderer) Refresh() {
	for _, o := range r.sv.objects {
		o.Refresh()
	}
}
