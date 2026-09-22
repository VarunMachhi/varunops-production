//go:build windows
package main

import (
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "syscall"
    "time"
    "unsafe"
)

const version = "1.0.0"

var (
    kernel32       = syscall.NewLazyDLL("kernel32.dll")
    procCreateMutexW = kernel32.NewProc("CreateMutexW")
    procCloseHandle  = kernel32.NewProc("CloseHandle")
)

func logf(format string, args ...any) {
    base := filepath.Join(os.Getenv("ProgramData"), "VarunOps")
    _ = os.MkdirAll(base, 0755)
    f, err := os.OpenFile(filepath.Join(base, "watchdog.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
    if err != nil { return }
    defer f.Close()
    _, _ = fmt.Fprintf(f, "%s "+format+"\r\n", append([]any{time.Now().Format(time.RFC3339)}, args...)...)
}

func acquireSingleton() (syscall.Handle, bool) {
    name, _ := syscall.UTF16PtrFromString("Global\\VarunOpsWatchdogSingleton")
    h, _, err := procCreateMutexW.Call(0, 0, uintptr(unsafe.Pointer(name)))
    if h == 0 { logf("CreateMutex failed: %v", err); return 0, false }
    if errno, ok := err.(syscall.Errno); ok && errno == 183 { // ERROR_ALREADY_EXISTS
        procCloseHandle.Call(h)
        return 0, false
    }
    return syscall.Handle(h), true
}

func main() {
    h, ok := acquireSingleton()
    if !ok { return }
    defer procCloseHandle.Call(uintptr(h))

    base := filepath.Join(os.Getenv("ProgramData"), "VarunOps")
    agent := filepath.Join(base, "VarunOpsAgent.ps1")
    logf("VarunOps watchdog %s started", version)

    for {
        if _, err := os.Stat(agent); err != nil {
            logf("Agent file missing: %v", err)
            time.Sleep(10 * time.Second)
            continue
        }
        cmd := exec.Command("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", agent)
        cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
        logf("Starting endpoint agent")
        if err := cmd.Start(); err != nil {
            logf("Failed to start agent: %v", err)
            time.Sleep(10 * time.Second)
            continue
        }
        err := cmd.Wait()
        if err != nil { logf("Agent exited: %v", err) } else { logf("Agent exited normally") }
        time.Sleep(3 * time.Second)
    }
}
