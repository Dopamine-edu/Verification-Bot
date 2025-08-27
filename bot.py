import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from firebase_admin import credentials, firestore, initialize_app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Firebase
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_app = initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully")
except Exception as e:
    logger.error(f"Error initializing Firebase: {e}")
    raise

# Telegram Bot Token
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    try:
        user = update.effective_user
        args = context.args
        
        if args:
            verification_code = args[0]
            await handle_verification(update, context, verification_code)
        else:
            # Ask for phone number if no verification code provided
            keyboard = [[KeyboardButton("Share Phone Number", request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                "Welcome to Dopamine Quiz Bot! 👋\n\n"
                "To verify your phone number, please share your contact using the button below.",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("An error occurred. Please try again.")

async def handle_verification(update: Update, context: ContextTypes.DEFAULT_TYPE, verification_code: str) -> None:
    """Handle verification code from the start command."""
    try:
        # Look up the verification code in Firestore
        verification_ref = db.collection('telegramVerifications').document(verification_code)
        verification_doc = verification_ref.get()
        
        if not verification_doc.exists:
            await update.message.reply_text("Invalid verification code. Please try again from the website.")
            return
        
        verification_data = verification_doc.to_dict()
        user_id = verification_data.get('userId')
        phone_number = verification_data.get('phone')
        
        if not user_id:
            await update.message.reply_text("Invalid verification data. Please try again from the website.")
            return
        
        # Get the user document to check if it exists
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            await update.message.reply_text("User not found. Please try again from the website.")
            return
        
        # Update user document in Firestore to mark phone as verified
        await user_ref.update({
            'phoneVerified': True,
            'telegramUsername': update.effective_user.username,
            'telegramId': update.effective_user.id
        })
        
        # Delete the verification code to prevent reuse
        verification_ref.delete()
        
        await update.message.reply_text(
            "✅ Your phone number has been verified successfully!\n\n"
            "You can now return to the website to continue."
        )
        
        logger.info(f"User {user_id} verified successfully via code {verification_code}")
        
    except Exception as e:
        logger.error(f"Error in handle_verification: {e}")
        await update.message.reply_text("An error occurred during verification. Please try again.")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the user's shared contact."""
    try:
        contact = update.message.contact
        user_id = contact.user_id
        
        if user_id and user_id != update.effective_user.id:
            await update.message.reply_text("Please share your own contact information.")
            return
        
        phone_number = contact.phone_number
        if not phone_number:
            await update.message.reply_text("No phone number found in contact.")
            return
        
        # Format phone number to standard format (remove + if present for comparison)
        formatted_phone = phone_number.lstrip('+')
        
        # Check if this phone number exists in any pending verification
        verifications_ref = db.collection('telegramVerifications')
        query = verifications_ref.where('phone', '>=', formatted_phone).where('phone', '<=', formatted_phone + '\uf8ff').stream()
        
        found = False
        for doc in query:
            verification_data = doc.to_dict()
            user_id = verification_data.get('userId')
            
            if not user_id:
                continue
                
            # Update user document
            user_ref = db.collection('users').document(user_id)
            await user_ref.update({
                'phoneVerified': True,
                'telegramUsername': update.effective_user.username,
                'telegramId': update.effective_user.id
            })
            
            # Delete the verification document
            doc.reference.delete()
            
            found = True
            logger.info(f"User {user_id} verified successfully via contact sharing")
        
        if found:
            await update.message.reply_text(
                "✅ Your phone number has been verified successfully!\n\n"
                "You can now return to the website to continue."
            )
        else:
            await update.message.reply_text(
                "No pending verification found for this phone number. "
                "Please start the verification process from the website first."
            )
            
    except Exception as e:
        logger.error(f"Error in handle_contact: {e}")
        await update.message.reply_text("An error occurred while processing your contact. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    try:
        await update.message.reply_text(
            "🤖 *Dopamine Quiz Bot Help*\n\n"
            "This bot helps verify your phone number for the Dopamine Quiz website.\n\n"
            "*How to use:*\n"
            "1. Start the verification process on the website\n"
            "2. Click the 'Verify via Telegram' button\n"
            "3. This bot will automatically verify your phone number\n\n"
            "If you have any issues, please contact support.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in help_command: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check verification status."""
    try:
        # Check if user exists in our database
        user_id = update.effective_user.id
        users_ref = db.collection('users')
        query = users_ref.where('telegramId', '==', user_id).stream()
        
        verified = False
        for doc in query:
            user_data = doc.to_dict()
            if user_data.get('phoneVerified'):
                verified = True
                break
        
        if verified:
            await update.message.reply_text(
                "✅ Your phone number is already verified!\n\n"
                "You can return to the website to continue."
            )
        else:
            await update.message.reply_text(
                "Your phone number is not yet verified.\n\n"
                "Please start the verification process from the website first."
            )
            
    except Exception as e:
        logger.error(f"Error in status_command: {e}")
        await update.message.reply_text("An error occurred while checking your status. Please try again.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started successfully")
    application.run_polling()

if __name__ == "__main__":
    main()
