import logging
from notion_token import Notion, SettingError
from gcal_token import Google


def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Initialize and test Notion class
        notion = Notion()
        notion.test_settings()  # You'll need to implement this method to test settings
        notion.get_string()  # This method should probably log instead of print

        # Initialize and test Google class
        google = Google()
        google.test_settings()  # Similarly, implement this to test settings in the Google class
        google.get_string()  # Adjust method name as necessary

    except SettingError as e:
        logger.error(e)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
