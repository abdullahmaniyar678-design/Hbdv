"""
MCQ Extractor Telegram Bot - Main File
Handles all Telegram interactions and message sending
"""

import os
import logging
import tempfile
import shutil
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from extractor import extract_mcqs_from_pdf

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token - replace with your actual token
BOT_TOKEN = "7613270526:AAGTPKjKHg8nKpEmliz3mZEwoFnHZRKjSOw"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when /start command is issued"""
    welcome_message = (
        "👋 **Welcome to MCQ Extractor Bot!**\n\n"
        "📚 I can extract Multiple Choice Questions from your PDF files.\n\n"
        "**How to use:**\n"
        "1️⃣ Upload a PDF file containing MCQs\n"
        "2️⃣ Wait while I extract the questions\n"
        "3️⃣ Receive formatted MCQs with topics, options, and answers\n\n"
        "✨ **Features:**\n"
        "• Extracts topics and questions\n"
        "• Detects correct answers\n"
        "• Extracts images from PDFs\n"
        "• Finds video links and explanations\n\n"
        "📤 Just send me a PDF to get started!"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF file uploads"""
    document = update.message.document
    
    # Check if the file is a PDF
    if not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text(
            "⚠️ Please send a PDF file only.\n"
            "Other file formats are not supported."
        )
        return
    
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    pdf_path = os.path.join(temp_dir, document.file_name)
    
    try:
        # Download the PDF
        await update.message.reply_text("📥 Downloading your file...")
        file = await document.get_file()
        await file.download_to_drive(pdf_path)
        
        # Extract MCQs
        await update.message.reply_text("🧠 Extracting MCQs, please wait...")
        logger.info(f"Processing PDF: {document.file_name}")
        
        extracted_data = extract_mcqs_from_pdf(pdf_path, temp_dir)
        
        # Check if extraction was successful
        if not extracted_data:
            await update.message.reply_text(
                "⚠️ Could not extract MCQs. Please try another file.\n\n"
                "Make sure your PDF contains:\n"
                "• Clear question numbers\n"
                "• Multiple choice options (A, B, C, D)\n"
                "• Readable text (not scanned images)"
            )
            return
        
        # Send extracted content
        await send_extracted_content(update, extracted_data)
        await update.message.reply_text("✅ Extraction complete!")
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        await update.message.reply_text(
            "❌ An error occurred while processing your file.\n"
            "Please try again or send a different PDF."
        )
    
    finally:
        # Clean up temporary files
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory: {str(e)}")


async def send_extracted_content(update: Update, data: list) -> None:
    """Send extracted MCQs to the chat in a formatted manner"""
    
    for topic_data in data:
        topic = topic_data.get('topic', 'General Questions')
        questions = topic_data.get('questions', [])
        
        if not questions:
            continue
        
        # Send topic header
        topic_message = f"📘 **Topic: {topic}**\n{'─' * 40}"
        await update.message.reply_text(topic_message, parse_mode='Markdown')
        
        # Send each question
        for idx, q in enumerate(questions, 1):
            await send_single_question(update, q, idx)
        
        # Add spacing between topics
        await update.message.reply_text("━" * 40)


async def send_single_question(update: Update, question_data: dict, q_num: int) -> None:
    """Send a single MCQ with all its components"""
    
    # Build question text
    question_text = f"❓ **Q{q_num}. {question_data.get('question', 'Question text not found')}**\n\n"
    
    # Add options
    options = question_data.get('options', [])
    option_labels = ['A)', 'B)', 'C)', 'D)', 'E)', 'F)']
    
    for i, option in enumerate(options):
        if i < len(option_labels):
            question_text += f"{option_labels[i]} {option}\n"
    
    # Add correct answer
    answer = question_data.get('answer')
    if answer:
        question_text += f"\n✅ **Correct Answer:** {answer}"
    
    # Send question text
    await update.message.reply_text(question_text, parse_mode='Markdown')
    
    # Send image if available
    image_path = question_data.get('image')
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, 'rb') as img_file:
                await update.message.reply_photo(photo=img_file, caption="🖼️ Question Image")
        except Exception as e:
            logger.error(f"Error sending image: {str(e)}")
    
    # Send video link if available
    video_link = question_data.get('video_link')
    if video_link:
        await update.message.reply_text(
            f"🎥 **Watch Explanation Video:**\n{video_link}",
            parse_mode='Markdown'
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again later."
        )


def main() -> None:
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
