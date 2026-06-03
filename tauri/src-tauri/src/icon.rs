//! Dynamic tray icon generation.
//!
//! Port of the original `task_stack.icon` Python module. Renders a 64x64 RGBA
//! image: a circular background whose color reflects the task count via
//! configurable thresholds, with the count drawn (capped at 99) as a centered
//! number. Digits are rendered with a built-in seven-segment glyph set so the
//! generator carries no font dependency.

use tiny_skia::{FillRule, Paint, PathBuilder, Pixmap, Rect, Transform};

const SIZE: u32 = 64;
const BG_EMPTY: (u8, u8, u8) = (120, 120, 120);

/// W3C relative luminance (WCAG 2.x); pick black or white text for contrast.
fn fg_for(bg: (u8, u8, u8)) -> (u8, u8, u8) {
    fn channel(c: u8) -> f64 {
        let s = c as f64 / 255.0;
        if s <= 0.04045 {
            s / 12.92
        } else {
            ((s + 0.055) / 1.055).powf(2.4)
        }
    }
    let (r, g, b) = bg;
    let l = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    if l > 0.179 {
        (0, 0, 0)
    } else {
        (255, 255, 255)
    }
}

fn color_for(count: usize, thresholds: &[(i64, (u8, u8, u8))]) -> (u8, u8, u8) {
    if count == 0 {
        return BG_EMPTY;
    }
    // Evaluate in descending order of min_count; first match wins.
    let mut sorted: Vec<&(i64, (u8, u8, u8))> = thresholds.iter().collect();
    sorted.sort_by(|a, b| b.0.cmp(&a.0));
    let mut color = thresholds.last().map(|t| t.1).unwrap_or(BG_EMPTY);
    if let Some(first) = thresholds.first() {
        color = first.1;
    }
    for (min_count, rgb) in sorted {
        if count as i64 >= *min_count {
            color = *rgb;
            break;
        }
    }
    color
}

fn fill_rect(pixmap: &mut Pixmap, x: f32, y: f32, w: f32, h: f32, color: (u8, u8, u8)) {
    let mut paint = Paint::default();
    paint.set_color_rgba8(color.0, color.1, color.2, 255);
    paint.anti_alias = true;
    if let Some(rect) = Rect::from_xywh(x, y, w, h) {
        pixmap.fill_rect(rect, &paint, Transform::identity(), None);
    }
}

/// Draw a single seven-segment digit in the box (x, y, w, h) with stroke
/// thickness `t`.
fn draw_digit(pixmap: &mut Pixmap, digit: u8, x: f32, y: f32, w: f32, h: f32, t: f32, color: (u8, u8, u8)) {
    // segment flags: a b c d e f g
    let seg: [bool; 7] = match digit {
        0 => [true, true, true, true, true, true, false],
        1 => [false, true, true, false, false, false, false],
        2 => [true, true, false, true, true, false, true],
        3 => [true, true, true, true, false, false, true],
        4 => [false, true, true, false, false, true, true],
        5 => [true, false, true, true, false, true, true],
        6 => [true, false, true, true, true, true, true],
        7 => [true, true, true, false, false, false, false],
        8 => [true, true, true, true, true, true, true],
        9 => [true, true, true, true, false, true, true],
        _ => [false; 7],
    };
    let half = t / 2.0;
    // a (top)
    if seg[0] {
        fill_rect(pixmap, x + half, y, w - t, t, color);
    }
    // b (top-right)
    if seg[1] {
        fill_rect(pixmap, x + w - t, y + half, t, h / 2.0 - half, color);
    }
    // c (bottom-right)
    if seg[2] {
        fill_rect(pixmap, x + w - t, y + h / 2.0, t, h / 2.0 - half, color);
    }
    // d (bottom)
    if seg[3] {
        fill_rect(pixmap, x + half, y + h - t, w - t, t, color);
    }
    // e (bottom-left)
    if seg[4] {
        fill_rect(pixmap, x, y + h / 2.0, t, h / 2.0 - half, color);
    }
    // f (top-left)
    if seg[5] {
        fill_rect(pixmap, x, y + half, t, h / 2.0 - half, color);
    }
    // g (middle)
    if seg[6] {
        fill_rect(pixmap, x + half, y + h / 2.0 - half, w - t, t, color);
    }
}

/// Returns (rgba_bytes, width, height).
pub fn make_icon(count: usize, thresholds: &[(i64, (u8, u8, u8))]) -> (Vec<u8>, u32, u32) {
    let color = color_for(count, thresholds);
    let mut pixmap = Pixmap::new(SIZE, SIZE).expect("alloc pixmap");

    // Filled circle background.
    let mut paint = Paint::default();
    paint.set_color_rgba8(color.0, color.1, color.2, 255);
    paint.anti_alias = true;
    let r = SIZE as f32 / 2.0;
    let mut pb = PathBuilder::new();
    pb.push_circle(r, r, r - 0.5);
    if let Some(path) = pb.finish() {
        pixmap.fill_path(&path, &paint, FillRule::Winding, Transform::identity(), None);
    }

    if count > 0 {
        let label = format!("{}", count.min(99));
        let fg = fg_for(color);
        // Mirror the Python sizing: 42px tall for one digit, 30px for two.
        let digit_h: f32 = if label.len() == 1 { 42.0 } else { 30.0 };
        let digit_w: f32 = digit_h * 0.58;
        let thickness: f32 = digit_h * 0.16;
        let gap: f32 = digit_h * 0.18;
        let total_w = digit_w * label.len() as f32 + gap * (label.len() as f32 - 1.0);
        let start_x = (SIZE as f32 - total_w) / 2.0;
        let start_y = (SIZE as f32 - digit_h) / 2.0;
        for (i, ch) in label.chars().enumerate() {
            let d = ch.to_digit(10).unwrap_or(0) as u8;
            let dx = start_x + i as f32 * (digit_w + gap);
            draw_digit(&mut pixmap, d, dx, start_y, digit_w, digit_h, thickness, fg);
        }
    }

    (pixmap.data().to_vec(), SIZE, SIZE)
}
