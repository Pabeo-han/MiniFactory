// Entry point for the portable Windows ZIP. Build with Zig on a host with
// the Windows GNU target. The separate build_windows.bat uses PyInstaller.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

static wchar_t directory[32768];
static wchar_t python[32768];
static wchar_t command[32768];

static int launch_error(const wchar_t *message) {
    MessageBoxW(NULL, message, L"MiniFactory", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show) {
    (void)instance;
    (void)previous;
    (void)show;

    DWORD length = GetModuleFileNameW(NULL, directory, ARRAYSIZE(directory));
    if (!length || length >= ARRAYSIZE(directory)) {
        return launch_error(L"Could not locate MiniFactory.exe.");
    }

    wchar_t *separator = wcsrchr(directory, L'\\');
    if (!separator) {
        return launch_error(L"Could not locate the MiniFactory folder.");
    }
    *separator = L'\0';
    const wchar_t *runtime = L"\\runtime\\pythonw.exe";
    const wchar_t *script = L"\\game\\play.pyw";
    size_t folder_size = wcslen(directory);
    if (folder_size + wcslen(runtime) >= ARRAYSIZE(python) ||
        folder_size * 2 + wcslen(runtime) + wcslen(script) + wcslen(args) + 8 >= ARRAYSIZE(command)) {
        return launch_error(L"Move the MiniFactory folder to a shorter path.");
    }
    wcscpy(python, directory);
    wcscat(python, runtime);

    wcscpy(command, L"\"");
    wcscat(command, python);
    wcscat(command, L"\" \"");
    wcscat(command, directory);
    wcscat(command, script);
    wcscat(command, L"\" ");
    wcscat(command, args);

    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, directory, &startup, &process)) {
        return launch_error(L"Could not start MiniFactory. Extract the entire ZIP and keep the runtime and game folders next to MiniFactory.exe.");
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exit_code = 1;
    GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hProcess);
    return (int)exit_code;
}
