import asyncio
import os
import signal

from dotenv import load_dotenv

from bot.bot import bot
from bot.handlers import set_bot_commands


# ----------------------------------run code----------------------------------
def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_old_instance(pid_file: str) -> None:
    if not os.path.exists(pid_file):
        return

    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            raw_pid = f.read().strip()
        old_pid = int(raw_pid)
    except Exception:
        # Corrupted or empty PID file. It will be overwritten.
        return

    current_pid = os.getpid()
    if old_pid <= 0 or old_pid == current_pid:
        return

    if not _pid_exists(old_pid):
        # Stale PID file.
        return

    try:
        os.kill(old_pid, signal.SIGTERM)
        print(f"Found old instance (PID {old_pid}). Terminated.")
    except Exception as e:
        print(f"Warning: failed to terminate old PID {old_pid}: {e}")


async def main() -> None:
    load_dotenv()

    pid_file = "bot.pid"
    _terminate_old_instance(pid_file)

    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

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
            except Exception as e:
                err = str(e).lower()

                # Catch 409 Conflict (duplicate bot instance)
                if "409" in err or ("conflict" in err and "terminated" in err):
                    print("\n\n" + "=" * 60)
                    print("CRITICAL ERROR: DUPLICATE BOT INSTANCE DETECTED")
                    print("=" * 60)
                    print("Telegram API returned '409 Conflict'.")
                    print("This means another copy of this bot is already running.")
                    print("ACTION REQUIRED: terminate the other instance first.")
                    print("=" * 60 + "\n")
                    await bot.close_session()
                    return

                wait_time = 10 if ("network" in err or "connection" in err) else 5
                print(f"Polling error. Retrying in {wait_time}s: {e}")
                await bot.close_session()
                await bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(wait_time)
    finally:
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped by user.")
# ----------------------------------------------------------------------------
