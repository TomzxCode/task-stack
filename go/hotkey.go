package main

import (
	"log"
	"sync"

	"golang.design/x/hotkey"
)

// HotkeyListener registers a global hotkey and invokes a callback when it
// fires. The registered hotkey can be replaced at runtime via Apply.
type HotkeyListener struct {
	callback func()

	mu     sync.Mutex
	hk     *hotkey.Hotkey
	doneCh chan struct{}
}

func NewHotkeyListener(callback func()) *HotkeyListener {
	return &HotkeyListener{callback: callback}
}

// Apply registers the given spec, replacing any previously registered hotkey.
func (l *HotkeyListener) Apply(spec HotkeySpec) {
	l.mu.Lock()
	if l.doneCh != nil {
		close(l.doneCh)
		l.doneCh = nil
	}
	if l.hk != nil {
		_ = l.hk.Unregister()
		l.hk = nil
	}
	l.mu.Unlock()

	hk := hotkey.New(spec.Mods, spec.Key)
	if err := hk.Register(); err != nil {
		log.Printf("hotkey register %q: %v", spec.Pretty, err)
		return
	}

	done := make(chan struct{})
	l.mu.Lock()
	l.hk = hk
	l.doneCh = done
	l.mu.Unlock()

	go func() {
		for {
			select {
			case <-hk.Keydown():
				if l.callback != nil {
					l.callback()
				}
			case <-done:
				return
			}
		}
	}()
}

// Stop unregisters the current hotkey and stops the listener goroutine.
func (l *HotkeyListener) Stop() {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.doneCh != nil {
		close(l.doneCh)
		l.doneCh = nil
	}
	if l.hk != nil {
		_ = l.hk.Unregister()
		l.hk = nil
	}
}
