import asyncio
from bot.bot import bot 
from bot.handlers import set_bot_commands 




# ----------------------------------run code----------------------------------
async def main() -> None:
    while True:
        try:
            await set_bot_commands(bot)
            await bot.infinity_polling(
                timeout=50,
                skip_pending=True,
                request_timeout=70,
            )
        except Exception as e:
            err = str(e).lower()
            wait_time = 10 if ("network" in err or "connection" in err) else 5
            print(f"Ошибка в polling, ждём {wait_time} секунд: {e}")
            await asyncio.sleep(wait_time)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Программа остановлена пользователем")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
# ----------------------------------------------------------------------------

