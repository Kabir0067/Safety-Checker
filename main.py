import asyncio
import os
import signal
from bot.bot import bot 
from bot.handlers import set_bot_commands 



from dotenv import load_dotenv

# ----------------------------------run code----------------------------------
async def main() -> None:
    load_dotenv()
    
    # PID File Management to kill zombie processes
    PID_FILE = "bot.pid"
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Check/Kill logic
            try:
                # signal 0 checks for existence on Unix, fails on Windows (handled below)
                if os.name != 'nt':
                    os.kill(old_pid, 0)
                
                print(f"⚠️ Found old instance (PID {old_pid}). Terminating...")
                os.kill(old_pid, signal.SIGTERM)
                print("✅ Old instance terminated.")
            except (ProcessLookupError, OSError):
                # Process dead or access denied
                pass
        except Exception as e:
            print(f"Warning: Failed to check/kill old PID: {e}")

    # Write current PID
    with open(PID_FILE, 'w') as f:
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
                
                # Catch 409 Conflict (Duplicate Instance)
                if "409" in err or "conflict" in err and "terminated" in err:
                    print("\n\n" + "="*60)
                    print("🛑 CRITICAL ERROR: DUPLICATE BOT INSTANCE DETECTED")
                    print("="*60)
                    print("Telegram API returned '409 Conflict'.")
                    print("This means another copy of this bot is ALREADY running.")
                    print("You typically have it running on:")
                    print("  1. Your local computer (Windows)")
                    print("  2. The server (Linux) - at the same time")
                    print("\n👉 ACTION REQUIRED: TERMINATE THE OTHER INSTANCE FIRST.")
                    print("="*60 + "\n")
                    # Exit strictly to prevent spamming the logs
                    await bot.close_session()
                    return

                wait_time = 10 if ("network" in err or "connection" in err) else 5
                print(f"Ошибка в polling, ждём {wait_time} секунд: {e}")
                await bot.close_session()
                await bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(wait_time)
    finally:
        # Cleanup PID file
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Программа остановлена пользователем")
# ----------------------------------------------------------------------------