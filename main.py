import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DJANGO_SETTINGS_MODULE = os.getenv("DJANGO_SETTINGS_MODULE") or "panel.settings"

DEFAULT_ADMIN_USER = "admin_checker"
DEFAULT_ADMIN_PASS = "111222"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_TZ = "Asia/Dushanbe"


def python_exe() -> str:
    return sys.executable or ("python.exe" if os.name == "nt" else "python3")


def pick_free_port(start: int) -> int:
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def try_open_windows_firewall_port(port: int) -> None:
    if os.name != "nt":
        return

    rule_name = f"SafetyChecker Admin {port}"
    try:
        check_cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "show",
            "rule",
            f"name={rule_name}",
        ]
        check = subprocess.run(check_cmd, capture_output=True, text=True)
        if check.returncode == 0 and "No rules match" not in (check.stdout + check.stderr):
            return

        add_cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={rule_name}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={port}",
        ]
        result = subprocess.run(add_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[ADMIN] Firewall rule added for TCP port {port}.")
        else:
            print("[ADMIN] Warning: failed to add firewall rule automatically.")
            print("[ADMIN] Please open TCP port manually in Windows Firewall.")
    except Exception:
        print("[ADMIN] Warning: firewall check failed. Open TCP port manually if needed.")


def popen(cmd: list[str], env: Optional[dict] = None, cwd: Optional[Path] = None) -> subprocess.Popen:
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            time.sleep(1)
            if proc.poll() is None:
                proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def run_database_migrate_or_exit() -> None:
    migrate_path = ROOT / "database" / "migrate.py"
    if not migrate_path.exists():
        print(f"[MIGRATE] ERROR: {migrate_path} not found")
        raise SystemExit(1)

    print("[MIGRATE] Running database migration (SQLAlchemy models)...")
    result = subprocess.run([python_exe(), str(migrate_path)], cwd=str(ROOT))
    if result.returncode != 0:
        print(f"[MIGRATE] FAILED with code {result.returncode}")
        raise SystemExit(result.returncode)
    print("[MIGRATE] OK")


def run_django_migrate_or_exit(env: dict) -> None:
    manage_py = ROOT / "manage.py"
    if not manage_py.exists():
        print("[DJANGO] ERROR: manage.py not found")
        raise SystemExit(1)

    print("[DJANGO] Running Django migrations (auth/admin/session)...")
    result = subprocess.run([python_exe(), "manage.py", "migrate", "--noinput"], cwd=str(ROOT), env=env)
    if result.returncode != 0:
        print(f"[DJANGO] FAILED with code {result.returncode}")
        raise SystemExit(result.returncode)
    print("[DJANGO] OK")


def ensure_django_superuser(username: str, password: str, email: str, env: dict) -> None:
    os.environ.update(env)

    try:
        import django

        django.setup()
    except Exception as exc:
        print(f"[ADMIN] ERROR: Django setup failed: {exc}")
        raise SystemExit(1)

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    existing = user_model.objects.filter(username=username).first()

    if existing:
        changed_fields = []
        if not existing.is_superuser:
            existing.is_superuser = True
            changed_fields.append("is_superuser")
        if not existing.is_staff:
            existing.is_staff = True
            changed_fields.append("is_staff")
        if changed_fields:
            existing.save(update_fields=changed_fields)
        print(f"[ADMIN] Superuser exists: {username}")
        return

    user_model.objects.create_superuser(username=username, email=email, password=password)
    print(f"[ADMIN] Superuser created: {username}")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_old_bot_instance(pid_file: Path) -> None:
    if not pid_file.exists():
        return

    try:
        old_pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return

    current_pid = os.getpid()
    if old_pid <= 0 or old_pid == current_pid:
        return

    if not _pid_exists(old_pid):
        return

    try:
        os.kill(old_pid, signal.SIGTERM)
        print(f"[BOT] Found old instance (PID {old_pid}). Terminated.")
    except Exception as exc:
        print(f"[BOT] Warning: failed to terminate old PID {old_pid}: {exc}")


async def run_bot_forever() -> None:
    from bot.bot import bot
    from bot.handlers import set_bot_commands

    pid_file = ROOT / "bot.pid"
    _terminate_old_bot_instance(pid_file)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    try:
        await bot.delete_webhook(drop_pending_updates=True)

        while True:
            try:
                await set_bot_commands(bot)
                await bot.infinity_polling(
                    timeout=50,
                    skip_pending=True,
                    request_timeout=70,
                )
            except asyncio.CancelledError:
                await bot.close_session()
                raise
            except Exception as exc:
                err = str(exc).lower()
                if ("409" in err) or ("conflict" in err and "terminated" in err):
                    print("\n" + "=" * 60)
                    print("CRITICAL: DUPLICATE BOT INSTANCE DETECTED (409 Conflict)")
                    print("Terminate the other bot instance first.")
                    print("=" * 60 + "\n")
                    await bot.close_session()
                    return

                wait_time = 10 if ("network" in err or "connection" in err) else 5
                print(f"[BOT] Polling error. Retry in {wait_time}s: {exc}")
                await bot.close_session()
                await bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(wait_time)
    finally:
        if pid_file.exists():
            try:
                pid_file.unlink()
            except Exception:
                pass


async def main() -> None:
    load_dotenv()

    os.environ.setdefault("TZ", os.getenv("DJANGO_TIME_ZONE", DEFAULT_TZ))
    if hasattr(time, "tzset"):
        try:
            time.tzset()
        except Exception:
            pass

    admin_env = dict(os.environ)
    admin_env["DJANGO_SETTINGS_MODULE"] = DJANGO_SETTINGS_MODULE

    run_database_migrate_or_exit()
    run_django_migrate_or_exit(admin_env)

    await asyncio.to_thread(
        ensure_django_superuser,
        os.getenv("DJANGO_ADMIN_USER") or DEFAULT_ADMIN_USER,
        os.getenv("DJANGO_ADMIN_PASS") or DEFAULT_ADMIN_PASS,
        os.getenv("DJANGO_ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL,
        admin_env,
    )

    requested_port = int(os.getenv("ADMIN_PORT") or 8001)
    admin_port = pick_free_port(requested_port)
    admin_host = os.getenv("ADMIN_HOST") or "0.0.0.0"
    public_host = os.getenv("ADMIN_PUBLIC_HOST") or get_lan_ip()

    if os.getenv("ADMIN_OPEN_FIREWALL", "1") == "1":
        try_open_windows_firewall_port(admin_port)

    print(f"[ADMIN] Starting on {admin_host}:{admin_port}")
    print(f"[ADMIN] Local URL: http://127.0.0.1:{admin_port}/admin")
    if admin_host in {"0.0.0.0", "::"}:
        print(f"[ADMIN] LAN URL: http://{public_host}:{admin_port}/admin")
        print("[ADMIN] For global internet access open port in firewall/router/cloud security group.")
    else:
        print(f"[ADMIN] URL: http://{admin_host}:{admin_port}/admin")
    print(f"[ADMIN] Login: {os.getenv('DJANGO_ADMIN_USER') or DEFAULT_ADMIN_USER}")

    admin_proc = popen(
        [python_exe(), "manage.py", "runserver", f"{admin_host}:{admin_port}"],
        env=admin_env,
        cwd=ROOT,
    )

    bot_task = asyncio.create_task(run_bot_forever())

    try:
        while True:
            if admin_proc.poll() is not None:
                raise RuntimeError(f"Django admin exited with code {admin_proc.poll()}")

            if bot_task.done():
                exc = bot_task.exception()
                if exc:
                    raise exc
                break

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SYS] Stopping by user...")
    except Exception as exc:
        print(f"\n[SYS] ERROR: {exc}\n[SYS] Stopping all...")
    finally:
        if not bot_task.done():
            bot_task.cancel()
            try:
                await bot_task
            except Exception:
                pass

        stop_process(admin_proc)
        try:
            admin_proc.wait(timeout=5)
        except Exception:
            pass

        print("[SYS] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
