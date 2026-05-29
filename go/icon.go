package main

import (
	"bytes"
	"image"
	"image/color"
	"image/png"
	"math"
	"os"
	"sort"
	"sync"

	"fyne.io/fyne/v2"
	"golang.org/x/image/font"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"
)

const iconSize = 64

// defaultIconThresholds lists (min_count, rgb) entries; the first whose count
// is satisfied (checked descending) wins. count==0 always renders grey.
func defaultIconThresholds() []IconThreshold {
	return []IconThreshold{
		{MinCount: 11, Color: RGB{200, 50, 50}}, // red
		{MinCount: 6, Color: RGB{220, 180, 0}},  // yellow
		{MinCount: 1, Color: RGB{70, 130, 180}}, // blue
	}
}

var bgEmpty = RGB{120, 120, 120}

var fontCandidates = []string{
	"C:/Windows/Fonts/arialbd.ttf",
	"C:/Windows/Fonts/arial.ttf",
	"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
	"/System/Library/Fonts/Helvetica.ttc",
}

var (
	fontOnce   sync.Once
	parsedFont *opentype.Font
)

func loadFont() *opentype.Font {
	fontOnce.Do(func() {
		for _, path := range fontCandidates {
			data, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			f, err := opentype.Parse(data)
			if err != nil {
				continue
			}
			parsedFont = f
			return
		}
	})
	return parsedFont
}

// relative luminance per WCAG; returns black/white for contrast.
func fgFor(bg RGB) color.RGBA {
	channel := func(c uint8) float64 {
		s := float64(c) / 255
		if s <= 0.04045 {
			return s / 12.92
		}
		return math.Pow((s+0.055)/1.055, 2.4)
	}
	l := 0.2126*channel(bg.R) + 0.7152*channel(bg.G) + 0.0722*channel(bg.B)
	if l > 0.179 {
		return color.RGBA{0, 0, 0, 255}
	}
	return color.RGBA{255, 255, 255, 255}
}

func iconColor(count int, thresholds []IconThreshold) RGB {
	if count == 0 {
		return bgEmpty
	}
	if len(thresholds) == 0 {
		thresholds = defaultIconThresholds()
	}
	// thresholds may arrive in any order; the Python default fallback is the
	// entry with the highest min_count, then descending search picks a match.
	sorted := make([]IconThreshold, len(thresholds))
	copy(sorted, thresholds)
	sort.SliceStable(sorted, func(i, j int) bool { return sorted[i].MinCount < sorted[j].MinCount })
	col := sorted[len(sorted)-1].Color
	for i := len(sorted) - 1; i >= 0; i-- {
		if count >= sorted[i].MinCount {
			col = sorted[i].Color
			break
		}
	}
	return col
}

// MakeIcon renders the tray badge image for the given task count.
func MakeIcon(count int, thresholds []IconThreshold) *image.RGBA {
	col := iconColor(count, thresholds)
	img := image.NewRGBA(image.Rect(0, 0, iconSize, iconSize))

	cx, cy := float64(iconSize)/2, float64(iconSize)/2
	r := float64(iconSize)/2 - 0.5
	fillCol := color.RGBA{col.R, col.G, col.B, 255}
	for y := 0; y < iconSize; y++ {
		for x := 0; x < iconSize; x++ {
			dx := float64(x) - cx + 0.5
			dy := float64(y) - cy + 0.5
			if math.Sqrt(dx*dx+dy*dy) <= r {
				img.SetRGBA(x, y, fillCol)
			}
		}
	}

	if count > 0 {
		n := count
		if n > 99 {
			n = 99
		}
		label := itoa(n)
		fontSize := 42.0
		if len(label) != 1 {
			fontSize = 30.0
		}
		drawCenteredLabel(img, label, fontSize, fgFor(col))
	}
	return img
}

func drawCenteredLabel(img *image.RGBA, label string, size float64, fg color.RGBA) {
	f := loadFont()
	if f == nil {
		return
	}
	face, err := opentype.NewFace(f, &opentype.FaceOptions{Size: size, DPI: 72})
	if err != nil {
		return
	}
	defer face.Close()

	d := &font.Drawer{Dst: img, Src: image.NewUniform(fg), Face: face}
	advance := d.MeasureString(label)
	w := advance.Round()
	m := face.Metrics()
	textHeight := (m.Ascent + m.Descent).Round()

	x := (iconSize - w) / 2
	baseline := (iconSize-textHeight)/2 + m.Ascent.Round()
	d.Dot = fixed.P(x, baseline)
	d.DrawString(label)
}

// MakeIconPNG encodes MakeIcon to PNG bytes.
func MakeIconPNG(count int, thresholds []IconThreshold) []byte {
	var buf bytes.Buffer
	_ = png.Encode(&buf, MakeIcon(count, thresholds))
	return buf.Bytes()
}

// MakeIconResource wraps the PNG as a Fyne resource for the tray.
func MakeIconResource(count int, thresholds []IconThreshold) fyne.Resource {
	return fyne.NewStaticResource("task-stack-icon.png", MakeIconPNG(count, thresholds))
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [3]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}
