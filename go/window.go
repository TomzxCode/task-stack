package main

import (
	"image/color"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"
)

const (
	rowHeight     = 28
	defaultWidth  = 480
	defaultHeight = 360
)

type insertPos int

const (
	insertFirst insertPos = iota
	insertNext
	insertLast
)

// StackWindow owns all window UI state, mirroring the Python StackWindow.
type StackWindow struct {
	app fyne.App
	win fyne.Window

	entry         *taskEntry
	descEntry     *widget.Entry
	descContainer *fyne.Container
	view          *stackView
	scroll        *container.Scroll

	onStackChange func()

	settings Settings
	theme    Theme

	tasks          []Task
	selected       map[int]bool
	lastSelected   map[int]bool
	anchor         int
	cursor         int
	descShownFor   int
	editingIndex   int
	dragStart      int
	dragY0         float32
	filterText     string
	visibleIndices []int

	suppressEntryChange bool
	visible             bool
}

func NewStackWindow(app fyne.App, onStackChange func()) *StackWindow {
	sw := &StackWindow{
		app:           app,
		onStackChange: onStackChange,
		settings:      LoadSettings(),
		selected:      map[int]bool{},
		lastSelected:  map[int]bool{},
		anchor:        -1,
		cursor:        -1,
		descShownFor:  -1,
		editingIndex:  -1,
		dragStart:     -1,
	}
	sw.theme = sw.detectTheme()

	sw.win = app.NewWindow("Task Stack")
	sw.win.SetCloseIntercept(sw.Hide)

	sw.entry = newTaskEntry(sw)
	sw.entry.OnChanged = sw.onEntryChanged

	sw.view = newStackView(sw)
	sw.scroll = container.NewVScroll(sw.view)

	sw.descEntry = widget.NewMultiLineEntry()
	sw.descEntry.SetPlaceHolder("Add a description…")
	sw.descEntry.Wrapping = fyne.TextWrapWord
	sw.descEntry.OnChanged = func(string) { sw.saveDesc() }
	sw.descContainer = container.NewStack(sw.descEntry)
	sw.descContainer.Hide()

	content := container.NewBorder(sw.entry, sw.descContainer, nil, nil, sw.scroll)
	sw.win.SetContent(content)

	sw.applyInitialGeometry()
	sw.Refresh()
	return sw
}

func (sw *StackWindow) detectTheme() Theme {
	if sw.app.Settings().ThemeVariant() == theme.VariantDark {
		return darkTheme
	}
	return lightTheme
}

func (sw *StackWindow) applyInitialGeometry() {
	if g := sw.settings.Window; g != nil && g.Width > 1 && g.Height > 1 {
		sw.win.Resize(fyne.NewSize(float32(g.Width), float32(g.Height)))
		return
	}
	sw.win.Resize(fyne.NewSize(defaultWidth, defaultHeight))
}

func (sw *StackWindow) captureGeometry() {
	size := sw.win.Canvas().Size()
	w, h := int(size.Width), int(size.Height)
	if w <= 1 || h <= 1 {
		return
	}
	cur := sw.settings.Window
	if cur != nil && cur.Width == w && cur.Height == h {
		return
	}
	// Fyne does not expose an absolute window position portably; persist size
	// and keep any previously stored x/y.
	x, y := 0, 0
	if cur != nil {
		x, y = cur.X, cur.Y
	}
	sw.settings.Window = &WindowGeometry{Width: w, Height: h, X: x, Y: y}
	SaveSettings(sw.settings)
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

func (sw *StackWindow) Show() {
	sw.theme = sw.detectTheme()
	sw.Refresh()
	sw.win.Show()
	sw.win.RequestFocus()
	sw.focusCanvas()
	sw.visible = true
}

func (sw *StackWindow) Hide() {
	sw.saveDesc()
	sw.captureGeometry()
	sw.win.Hide()
	sw.visible = false
}

func (sw *StackWindow) IsVisible() bool { return sw.visible }

func (sw *StackWindow) Refresh() {
	sw.tasks = Load()
	sw.selected = map[int]bool{}
	sw.anchor = -1
	sw.cursor = -1
	sw.descShownFor = -1
	sw.cancelEdit()
	sw.filterText = ""
	sw.suppressEntryChange = true
	sw.entry.SetText("")
	sw.suppressEntryChange = false
	sw.redraw()
}

func (sw *StackWindow) focusCanvas() { sw.win.Canvas().Focus(sw.view) }

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

func (sw *StackWindow) fontSize() float32 { return float32(sw.settings.FontSize) }

func (sw *StackWindow) measure(text string, bold bool) fyne.Size {
	return fyne.MeasureText(text, sw.fontSize(), fyne.TextStyle{Bold: bold})
}

func (sw *StackWindow) truncate(text string, maxPx float32, bold bool) string {
	if sw.measure(text, bold).Width <= maxPx {
		return text
	}
	const ell = "…"
	r := []rune(text)
	for end := len(r) - 1; end > 0; end-- {
		cand := string(r[:end]) + ell
		if sw.measure(cand, bold).Width <= maxPx {
			return cand
		}
	}
	return ell
}

func (sw *StackWindow) newText(label string, col color.Color, bold bool) *canvas.Text {
	t := canvas.NewText(label, col)
	t.TextSize = sw.fontSize()
	t.TextStyle = fyne.TextStyle{Bold: bold}
	return t
}

func (sw *StackWindow) redraw() {
	t := sw.theme
	width := sw.view.width
	if width <= 1 {
		width = defaultWidth
	}

	objs := []fyne.CanvasObject{}

	rightPad := float32(8)
	gap := float32(8)
	durColW := sw.measure("00h 00m", false).Width + 8
	tsColW := sw.measure("00-00 00:00", false).Width + 8
	lcColW := tsColW
	idxColW := sw.measure("999", false).Width + 4
	execColW := sw.measure("×99", false).Width + 4

	durX := width - rightPad
	lcX := durX - durColW - gap
	tsX := lcX - lcColW - gap
	execX := tsX - tsColW - gap
	textRight := execX - execColW - gap

	now := time.Now()

	if sw.filterText != "" {
		sw.visibleIndices = sw.visibleIndices[:0]
		for idx, task := range sw.tasks {
			if fuzzyMatch(sw.filterText, task.Text) {
				sw.visibleIndices = append(sw.visibleIndices, idx)
			}
		}
	} else {
		sw.visibleIndices = sw.visibleIndices[:0]
		for i := range sw.tasks {
			sw.visibleIndices = append(sw.visibleIndices, i)
		}
	}

	rightText := func(label string, rightX, y0 float32, col color.Color) {
		txt := sw.newText(label, col, false)
		sz := sw.measure(label, false)
		txt.Move(fyne.NewPos(rightX-sz.Width, y0+(rowHeight-sz.Height)/2))
		objs = append(objs, txt)
	}

	for row, i := range sw.visibleIndices {
		task := sw.tasks[i]
		y0 := float32(row) * rowHeight

		bgCol := t.Bg
		if sw.selected[i] {
			bgCol = t.SelectedBg
		}
		rect := canvas.NewRectangle(bgCol)
		rect.Move(fyne.NewPos(0, y0))
		rect.Resize(fyne.NewSize(width, rowHeight))
		objs = append(objs, rect)

		for _, dy := range []float32{8, 13, 18} {
			ln := canvas.NewLine(t.DragHandle)
			ln.StrokeWidth = 1.5
			ln.Position1 = fyne.NewPos(8, y0+dy)
			ln.Position2 = fyne.NewPos(18, y0+dy)
			objs = append(objs, ln)
		}

		bold := i == 0

		idxTxt := sw.newText(itoa(i), t.FgMuted, bold)
		idxSz := sw.measure(itoa(i), bold)
		idxTxt.Move(fyne.NewPos(22, y0+(rowHeight-idxSz.Height)/2))
		objs = append(objs, idxTxt)

		indicatorX := float32(22) + idxColW
		indicator := "○"
		if i == 0 {
			indicator = "●"
		}
		indTxt := sw.newText(indicator, t.Fg, false)
		indSz := sw.measure(indicator, false)
		indTxt.Move(fyne.NewPos(indicatorX, y0+(rowHeight-indSz.Height)/2))
		objs = append(objs, indTxt)

		noteX := indicatorX + 20
		var textX float32
		if task.Description != "" {
			noteTxt := sw.newText("✎", t.FgDim, false)
			noteSz := sw.measure("✎", false)
			noteTxt.Move(fyne.NewPos(noteX, y0+(rowHeight-noteSz.Height)/2))
			objs = append(objs, noteTxt)
			textX = noteX + 18
		} else {
			textX = noteX + 2
		}

		textWidth := textRight - textX
		if textWidth < 0 {
			textWidth = 0
		}
		label := sw.truncate(task.Text, textWidth, bold)
		labelTxt := sw.newText(label, t.Fg, bold)
		labelSz := sw.measure(label, bold)
		labelTxt.Move(fyne.NewPos(textX, y0+(rowHeight-labelSz.Height)/2))
		objs = append(objs, labelTxt)

		var colFill color.Color = t.FgMuted
		var durSeconds float64
		if i == 0 {
			colFill = t.FgDim
			durSeconds = task.LiveDuration(now)
		} else {
			durSeconds = task.Duration
		}
		execText := "—"
		if task.ExecutionCount != 0 {
			execText = "×" + itoa(task.ExecutionCount)
		}
		rightText(execText, execX, y0, colFill)
		rightText(FormatTimestamp(task.StartedAt, now), tsX, y0, colFill)
		rightText(FormatTimestamp(task.LastCurrent, now), lcX, y0, colFill)
		rightText(FormatDuration(durSeconds), durX, y0, colFill)
	}

	if len(sw.tasks) == 0 {
		msg := sw.newText("No tasks — type above and press Enter", t.FgMuted, false)
		sz := sw.measure(msg.Text, false)
		msg.Move(fyne.NewPos((width-sz.Width)/2, (rowHeight-sz.Height)/2))
		objs = append(objs, msg)
	} else if len(sw.visibleIndices) == 0 {
		msg := sw.newText("No matching tasks", t.FgMuted, false)
		sz := sw.measure(msg.Text, false)
		msg.Move(fyne.NewPos((width-sz.Width)/2, (rowHeight-sz.Height)/2))
		objs = append(objs, msg)
	}

	height := float32(len(sw.visibleIndices)) * rowHeight
	if height < rowHeight {
		height = rowHeight
	}
	sw.view.setObjects(objs, height)

	sw.syncSelectionSideEffects()
}

// syncSelectionSideEffects mirrors the tail of the Python redraw: it pushes the
// selected task's text into the entry and shows/hides the description panel.
func (sw *StackWindow) syncSelectionSideEffects() {
	if !setsEqual(sw.selected, sw.lastSelected) {
		sw.lastSelected = copySet(sw.selected)
		if len(sw.selected) == 1 {
			sole := soleOf(sw.selected)
			if sole >= 0 && sole < len(sw.tasks) && sw.editingIndex < 0 {
				sw.suppressEntryChange = true
				sw.entry.SetText(sw.tasks[sole].Text)
				sw.suppressEntryChange = false
				sw.filterText = ""
			}
		} else if sw.editingIndex < 0 {
			sw.suppressEntryChange = true
			sw.entry.SetText("")
			sw.suppressEntryChange = false
			sw.filterText = ""
		}
	}

	if len(sw.selected) == 1 {
		sole := soleOf(sw.selected)
		if sole >= 0 && sole < len(sw.tasks) {
			sw.showDescPanel(sole)
			return
		}
	}
	sw.hideDescPanel()
}

// ---------------------------------------------------------------------------
// Description panel
// ---------------------------------------------------------------------------

func (sw *StackWindow) showDescPanel(idx int) {
	if sw.descShownFor == idx {
		return
	}
	sw.descShownFor = idx
	sw.suppressEntryChange = true
	sw.descEntry.SetText(sw.tasks[idx].Description)
	sw.suppressEntryChange = false
	sw.descContainer.Show()
	sw.descContainer.Refresh()
}

func (sw *StackWindow) hideDescPanel() {
	if sw.descShownFor < 0 {
		return
	}
	sw.descShownFor = -1
	sw.descContainer.Hide()
	sw.descContainer.Refresh()
}

func (sw *StackWindow) saveDesc() {
	if sw.suppressEntryChange {
		return
	}
	idx := sw.descShownFor
	if idx < 0 || idx >= len(sw.tasks) {
		return
	}
	sw.tasks = UpdateDescription(idx, sw.descEntry.Text)
}

// ---------------------------------------------------------------------------
// Entry handling
// ---------------------------------------------------------------------------

func (sw *StackWindow) onEntryChanged(s string) {
	if sw.suppressEntryChange {
		return
	}
	if sw.editingIndex >= 0 || len(sw.selected) > 0 {
		return
	}
	if s == sw.filterText {
		return
	}
	sw.filterText = s
	sw.redraw()
}

func (sw *StackWindow) submitEntry(position insertPos) {
	text := trim(sw.entry.Text)
	editIdx := sw.editingIndex
	if editIdx < 0 && len(sw.selected) == 1 {
		sole := soleOf(sw.selected)
		if sole >= 0 && sole < len(sw.tasks) {
			editIdx = sole
		}
	}
	if editIdx >= 0 {
		if text == "" {
			sw.cancelEdit()
			sw.redraw()
			return
		}
		sw.tasks = UpdateText(editIdx, text)
		sw.editingIndex = -1
		sw.selected = map[int]bool{}
		if editIdx >= 0 && editIdx < len(sw.tasks) {
			sw.selected[editIdx] = true
			sw.anchor = editIdx
		} else {
			sw.anchor = -1
		}
		sw.cursor = sw.anchor
		sw.lastSelected = copySet(sw.selected)
		sw.redraw()
		sw.onStackChange()
		sw.focusCanvas()
		return
	}
	if text == "" {
		return
	}
	sw.suppressEntryChange = true
	sw.entry.SetText("")
	sw.suppressEntryChange = false
	sw.filterText = ""
	switch position {
	case insertNext:
		sw.tasks = PushNext(text)
	case insertLast:
		sw.tasks = PushLast(text)
	default:
		sw.tasks = Push(text)
	}
	sw.selected = map[int]bool{}
	sw.anchor = -1
	sw.cursor = -1
	sw.redraw()
	sw.onStackChange()
	sw.focusCanvas()
}

func (sw *StackWindow) beginEdit(idx int) {
	if idx < 0 || idx >= len(sw.tasks) {
		return
	}
	sw.editingIndex = idx
	sw.selected = map[int]bool{idx: true}
	sw.anchor = idx
	sw.cursor = idx
	sw.suppressEntryChange = true
	sw.entry.SetText(sw.tasks[idx].Text)
	sw.suppressEntryChange = false
	sw.win.Canvas().Focus(sw.entry)
	sw.redraw()
}

func (sw *StackWindow) cancelEdit() {
	if sw.editingIndex < 0 {
		return
	}
	sw.editingIndex = -1
	sw.suppressEntryChange = true
	sw.entry.SetText("")
	sw.suppressEntryChange = false
}

func (sw *StackWindow) onEntryEscape() {
	if sw.entry.Text != "" {
		sw.cancelEdit()
		sw.suppressEntryChange = true
		sw.entry.SetText("")
		sw.suppressEntryChange = false
		sw.filterText = ""
		sw.selected = map[int]bool{}
		sw.anchor = -1
		sw.cursor = -1
		sw.lastSelected = map[int]bool{}
		sw.redraw()
		return
	}
	sw.focusCanvas()
}

// ---------------------------------------------------------------------------
// Canvas key / rune handling
// ---------------------------------------------------------------------------

func (sw *StackWindow) onCanvasRune(r rune) {
	if r == '?' {
		sw.ShowHelp()
		return
	}
	if r >= '0' && r <= '9' {
		return // handled in onCanvasKey (shift-immune)
	}
	if r < 0x20 {
		return
	}
	if len(sw.selected) == 1 {
		sole := soleOf(sw.selected)
		sw.beginEdit(sole)
		sw.suppressEntryChange = true
		sw.entry.SetText(string(r))
		sw.suppressEntryChange = false
	} else {
		sw.cancelEdit()
		sw.win.Canvas().Focus(sw.entry)
		sw.entry.SetText(string(r))
		sw.filterText = sw.entry.Text
		if len(sw.selected) > 0 {
			sw.selected = map[int]bool{}
			sw.anchor = -1
			sw.cursor = -1
			sw.lastSelected = map[int]bool{}
		}
		sw.redraw()
	}
}

func (sw *StackWindow) onCanvasKey(ev *fyne.KeyEvent, shift bool) {
	switch ev.Name {
	case fyne.KeyReturn, fyne.KeyEnter:
		if len(sw.selected) == 1 {
			sw.beginEdit(soleOf(sw.selected))
		}
		return
	}

	if d, ok := digitFromKey(ev.Name); ok {
		sw.selectByDigit(d, shift)
		return
	}

	switch ev.Name {
	case fyne.KeyUp, fyne.KeyDown:
		sw.moveSelection(ev.Name == fyne.KeyDown, shift)
		return
	case fyne.KeyEscape:
		sw.onCanvasEscape()
		return
	}

	if len(sw.selected) == 0 {
		return
	}
	sole := -1
	if len(sw.selected) == 1 {
		sole = soleOf(sw.selected)
	}

	switch ev.Name {
	case fyne.KeyLeft, fyne.KeyRight:
		if sole < 0 {
			return
		}
		delta := -1
		if ev.Name == fyne.KeyRight {
			delta = 1
		}
		newIdx := sole + delta
		if newIdx >= 0 && newIdx < len(sw.tasks) {
			sw.cancelEdit()
			sw.tasks = Reorder(sole, newIdx)
			sw.selected = map[int]bool{newIdx: true}
			sw.anchor = newIdx
			sw.cursor = newIdx
			sw.redraw()
			sw.onStackChange()
		}
	case fyne.KeyHome:
		if sole < 0 {
			return
		}
		sw.cancelEdit()
		sw.tasks = Promote(sole)
		sw.clearSelection()
		sw.redraw()
		sw.onStackChange()
	case fyne.KeyEnd:
		if sole < 0 {
			return
		}
		sw.cancelEdit()
		sw.tasks = Reorder(sole, len(sw.tasks)-1)
		sw.clearSelection()
		sw.redraw()
		sw.onStackChange()
	case fyne.KeyBackspace, fyne.KeyDelete:
		sw.deleteSelected()
	}
}

func (sw *StackWindow) deleteSelected() {
	sw.cancelEdit()
	minDeleted := -1
	for i := range sw.selected {
		if minDeleted < 0 || i < minDeleted {
			minDeleted = i
		}
	}
	sw.tasks = RemoveMany(sw.selected)
	sw.hideDescPanel()
	sw.lastSelected = map[int]bool{}
	sw.suppressEntryChange = true
	sw.entry.SetText("")
	sw.suppressEntryChange = false
	if len(sw.tasks) > 0 {
		next := minDeleted
		if next > len(sw.tasks)-1 {
			next = len(sw.tasks) - 1
		}
		sw.selected = map[int]bool{next: true}
		sw.anchor = next
		sw.cursor = next
	} else {
		sw.clearSelection()
	}
	sw.redraw()
	sw.onStackChange()
}

func (sw *StackWindow) onCanvasEscape() {
	if len(sw.selected) > 0 || sw.filterText != "" {
		sw.selected = map[int]bool{}
		sw.anchor = -1
		sw.cursor = -1
		if sw.editingIndex < 0 {
			sw.suppressEntryChange = true
			sw.entry.SetText("")
			sw.suppressEntryChange = false
			sw.filterText = ""
		}
		sw.redraw()
		return
	}
	sw.Hide()
}

func (sw *StackWindow) selectByDigit(digit int, shift bool) {
	visible := sw.visible_or_all()
	if digit >= len(visible) {
		return
	}
	realIdx := visible[digit]
	sw.saveDesc()
	if shift {
		if sw.anchor < 0 {
			sw.anchor = realIdx
		}
		sw.cursor = realIdx
		sw.selected = rangeSet(sw.anchor, sw.cursor)
	} else {
		sw.anchor = realIdx
		sw.cursor = realIdx
		sw.selected = map[int]bool{realIdx: true}
	}
	sw.focusCanvas()
	sw.redraw()
}

func (sw *StackWindow) moveSelection(down, shift bool) {
	sw.saveDesc()
	delta := -1
	if down {
		delta = 1
	}
	visible := sw.visible_or_all()
	if len(visible) == 0 {
		return
	}
	if shift {
		if sw.anchor < 0 {
			if down {
				sw.anchor = visible[0]
			} else {
				sw.anchor = visible[len(visible)-1]
			}
			sw.cursor = sw.anchor
		}
		cursorPos := sw.cursor
		if cursorPos < 0 {
			cursorPos = sw.anchor
		}
		curV := indexOf(visible, cursorPos)
		if curV < 0 {
			curV = 0
		}
		newV := clamp(curV+delta, 0, len(visible)-1)
		sw.cursor = visible[newV]
		sw.selected = rangeSet(sw.anchor, sw.cursor)
	} else {
		var pos int
		if len(sw.selected) == 0 {
			if down {
				pos = visible[0]
			} else {
				pos = visible[len(visible)-1]
			}
		} else {
			cur := sw.cursor
			if cur < 0 {
				cur = minOf(sw.selected)
			}
			curV := indexOf(visible, cur)
			if curV < 0 {
				curV = 0
			}
			newV := clamp(curV+delta, 0, len(visible)-1)
			pos = visible[newV]
		}
		sw.anchor = pos
		sw.cursor = pos
		sw.selected = map[int]bool{pos: true}
	}
	sw.focusCanvas()
	sw.redraw()
}

// ---------------------------------------------------------------------------
// Mouse / drag handling
// ---------------------------------------------------------------------------

func (sw *StackWindow) rowAt(y float32) int {
	if len(sw.visibleIndices) == 0 {
		return clamp(int(y/rowHeight), 0, max(0, len(sw.tasks)-1))
	}
	row := clamp(int(y/rowHeight), 0, len(sw.visibleIndices)-1)
	return sw.visibleIndices[row]
}

func (sw *StackWindow) dragPress(row int, y float32) {
	if len(sw.tasks) == 0 {
		return
	}
	sw.saveDesc()
	sw.focusCanvas()
	sw.dragStart = row
	sw.dragY0 = y
}

func (sw *StackWindow) dragMotion(y float32) {
	if sw.dragStart < 0 || len(sw.tasks) < 2 {
		return
	}
	target := sw.rowAt(y)
	if target == sw.dragStart {
		return
	}
	sw.cancelEdit()
	src := sw.dragStart
	var group map[int]bool
	if sw.selected[src] && len(sw.selected) > 1 {
		group = copySet(sw.selected)
	} else {
		group = map[int]bool{src: true}
	}
	var indexMap map[int]int
	sw.tasks, indexMap = ReorderGroup(group, src, target)

	remap := func(i int) int {
		if v, ok := indexMap[i]; ok {
			return v
		}
		return i
	}
	newSel := map[int]bool{}
	for i := range sw.selected {
		newSel[remap(i)] = true
	}
	sw.selected = newSel
	if sw.anchor >= 0 {
		sw.anchor = remap(sw.anchor)
	}
	if sw.cursor >= 0 {
		sw.cursor = remap(sw.cursor)
	}
	if sw.descShownFor >= 0 {
		sw.descShownFor = remap(sw.descShownFor)
	}
	sw.lastSelected = copySet(sw.selected)
	sw.dragStart = remap(src)
	sw.redraw()
	sw.onStackChange()
}

func (sw *StackWindow) dragRelease() {
	sw.dragStart = -1
}

func (sw *StackWindow) clickSelect(row int, shift bool) {
	if len(sw.tasks) == 0 {
		return
	}
	if shift {
		if sw.anchor < 0 {
			sw.anchor = row
		}
		sw.cursor = row
		sw.selected = rangeSet(sw.anchor, sw.cursor)
	} else {
		sw.anchor = row
		sw.cursor = row
		sw.selected = map[int]bool{row: true}
	}
	sw.redraw()
}

// ---------------------------------------------------------------------------
// Help
// ---------------------------------------------------------------------------

func (sw *StackWindow) ShowHelp() {
	rows := [][2]string{
		{"Typing", "Focus entry and type"},
		{"Enter", "Add task to top  /  Save edit"},
		{"Shift+Enter", "Insert task after current"},
		{"Home", "Add task to top  /  Promote selected to top"},
		{"End", "Add task to bottom  /  Send selected to bottom"},
		{"0-9", "Select task by index"},
		{"Shift+0-9 / Shift+↑↓", "Extend selection (range)"},
		{"Shift+click", "Extend selection to clicked row"},
		{"Up / Down", "Move selection"},
		{"Left / Right", "Move selected task up / down one position"},
		{"Return", "Edit selected task"},
		{"Escape", "Cancel edit  /  Hide window"},
		{"Backspace / Del", "Delete selected task(s)"},
		{"?", "Show this help"},
	}
	grid := container.New(layoutTwoCol{})
	for _, r := range rows {
		key := widget.NewLabelWithStyle(r[0], fyne.TextAlignLeading,
			fyne.TextStyle{Bold: true, Monospace: true})
		desc := widget.NewLabel(r[1])
		grid.Add(key)
		grid.Add(desc)
	}
	help := sw.app.NewWindow("Keyboard Shortcuts")
	help.SetContent(container.NewVScroll(grid))
	help.Resize(fyne.NewSize(420, 460))
	help.Show()
}

// layoutTwoCol arranges children in two columns (key, description) per row.
type layoutTwoCol struct{}

func (layoutTwoCol) MinSize(objs []fyne.CanvasObject) fyne.Size {
	var keyW, descW, h float32
	for i := 0; i+1 < len(objs); i += 2 {
		ks := objs[i].MinSize()
		ds := objs[i+1].MinSize()
		if ks.Width > keyW {
			keyW = ks.Width
		}
		if ds.Width > descW {
			descW = ds.Width
		}
		rh := ks.Height
		if ds.Height > rh {
			rh = ds.Height
		}
		h += rh
	}
	return fyne.NewSize(keyW+descW+24, h)
}

func (layoutTwoCol) Layout(objs []fyne.CanvasObject, size fyne.Size) {
	var keyW float32
	for i := 0; i+1 < len(objs); i += 2 {
		if w := objs[i].MinSize().Width; w > keyW {
			keyW = w
		}
	}
	var y float32
	for i := 0; i+1 < len(objs); i += 2 {
		ks := objs[i].MinSize()
		ds := objs[i+1].MinSize()
		rh := ks.Height
		if ds.Height > rh {
			rh = ds.Height
		}
		objs[i].Resize(fyne.NewSize(keyW, rh))
		objs[i].Move(fyne.NewPos(0, y))
		objs[i+1].Resize(fyne.NewSize(size.Width-keyW-16, rh))
		objs[i+1].Move(fyne.NewPos(keyW+16, y))
		y += rh
	}
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

func (sw *StackWindow) visible_or_all() []int {
	if len(sw.visibleIndices) > 0 {
		out := make([]int, len(sw.visibleIndices))
		copy(out, sw.visibleIndices)
		return out
	}
	out := make([]int, len(sw.tasks))
	for i := range sw.tasks {
		out[i] = i
	}
	return out
}

func (sw *StackWindow) clearSelection() {
	sw.selected = map[int]bool{}
	sw.anchor = -1
	sw.cursor = -1
}

func fuzzyMatch(query, text string) bool {
	if query == "" {
		return true
	}
	q := []rune(toLower(query))
	t := []rune(toLower(text))
	i := 0
	for _, ch := range t {
		if ch == q[i] {
			i++
			if i == len(q) {
				return true
			}
		}
	}
	return false
}

func toLower(s string) string {
	b := []rune(s)
	for i, r := range b {
		if r >= 'A' && r <= 'Z' {
			b[i] = r + 32
		}
	}
	return string(b)
}

func digitFromKey(name fyne.KeyName) (int, bool) {
	switch name {
	case fyne.Key0:
		return 0, true
	case fyne.Key1:
		return 1, true
	case fyne.Key2:
		return 2, true
	case fyne.Key3:
		return 3, true
	case fyne.Key4:
		return 4, true
	case fyne.Key5:
		return 5, true
	case fyne.Key6:
		return 6, true
	case fyne.Key7:
		return 7, true
	case fyne.Key8:
		return 8, true
	case fyne.Key9:
		return 9, true
	}
	return 0, false
}

func setsEqual(a, b map[int]bool) bool {
	if len(a) != len(b) {
		return false
	}
	for k := range a {
		if !b[k] {
			return false
		}
	}
	return true
}

func copySet(s map[int]bool) map[int]bool {
	out := make(map[int]bool, len(s))
	for k, v := range s {
		out[k] = v
	}
	return out
}

func soleOf(s map[int]bool) int {
	for k := range s {
		return k
	}
	return -1
}

func minOf(s map[int]bool) int {
	m := -1
	for k := range s {
		if m < 0 || k < m {
			m = k
		}
	}
	return m
}

func rangeSet(a, b int) map[int]bool {
	if a > b {
		a, b = b, a
	}
	out := make(map[int]bool, b-a+1)
	for i := a; i <= b; i++ {
		out[i] = true
	}
	return out
}

func indexOf(s []int, v int) int {
	for i, x := range s {
		if x == v {
			return i
		}
	}
	return -1
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}
