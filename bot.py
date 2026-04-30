from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import os

from events.router import route_callback, route_message

TOKEN = os.getenv("BOT_TOKEN")

application = Application.builder().token(TOKEN).build()

# ONLY ROUTING
application.add_handler(CommandHandler("start", route_message))
application.add_handler(CallbackQueryHandler(route_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))


if __name__ == "__main__":
    application.run_polling()