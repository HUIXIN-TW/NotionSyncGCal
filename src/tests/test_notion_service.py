import unittest
from unittest.mock import patch, Mock
from datetime import datetime
import notion.notion_services as ns

class TestNotionService(unittest.TestCase):
    # def __init__(self, page_id):
    #     self.page_id = input("Please enter the Notion page ID: ")
    #     print(f'You will use this page ID: {self.page_id} for testing, please make sure it is a valid page ID and not production page ID.')
    #     input("Press Enter to continue...")

    @patch('notion.notion_services.nt.NOTION.pages.retrieve')
    def test_get_task_by_id(self, mock_retrieve):
        # Arrange
        mock_retrieve.return_value = {'id': self.page_id, 'properties': {}}

        # Act
        result = ns.get_task_by_id(self.page_id)

        # Assert
        self.assertEqual(result['id'], self.page_id)
        mock_retrieve.assert_called_once_with(page_id=self.page_id)

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_notion_update(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {'title': {'title': [{'text': {'content': 'Updated Task'}}]}}}
        page_id = 'page_123'
        properties = {'title': {'title': [{'text': {'content': 'Updated Task'}}]}}

        # Act
        result = ns.notion_update(page_id, properties)

        # Assert
        self.assertEqual(result['properties']['title']['title'][0]['text']['content'], 'Updated Task')
        mock_update.assert_called_once_with(page_id=page_id, properties=properties)

    @patch('notion.notion_services.nt.NOTION.pages.create')
    def test_notion_create(self, mock_create):
        # Arrange
        mock_create.return_value = {'id': 'page_123', 'properties': {'title': {'title': [{'text': {'content': 'New Task'}}]}}}
        database_id = 'database_123'
        properties = {'title': {'title': [{'text': {'content': 'New Task'}}]}}

        # Act
        result = ns.notion_create(database_id, properties)

        # Assert
        self.assertEqual(result['properties']['title']['title'][0]['text']['content'], 'New Task')
        mock_create.assert_called_once_with(parent={'database_id': database_id}, properties=properties)

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_notion_delete(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {ns.nt.DELETE_NOTION_NAME: {'checkbox': True}}}
        page_id = 'page_123'

        # Act
        result = ns.notion_delete(page_id)

        # Assert
        self.assertTrue(result['properties'][ns.nt.DELETE_NOTION_NAME]['checkbox'])
        mock_update.assert_called_once_with(page_id=page_id, properties={ns.nt.DELETE_NOTION_NAME: {'checkbox': True}})

    @patch('notion.notion_services.nt.NOTION.databases.query')
    def test_queryNotionEvent_all(self, mock_query):
        # Arrange
        mock_query.return_value = {'results': [{'id': 'page_123'}]}

        # Act
        result = ns.queryNotionEvent_all()

        # Assert
        self.assertEqual(result, [{'id': 'page_123'}])
        mock_query.assert_called_once()

    @patch('notion.notion_services.nt.NOTION.databases.query')
    def test_queryNotionEvent_gcal(self, mock_query):
        # Arrange
        mock_query.return_value = {'results': [{'id': 'page_123'}]}

        # Act
        result = ns.queryNotionEvent_gcal()

        # Assert
        self.assertEqual(result, [{'id': 'page_123'}])
        mock_query.assert_called_once()

    @patch('notion.notion_services.nt.NOTION.databases.query')
    def test_queryNotionEvent_delete(self, mock_query):
        # Arrange
        mock_query.return_value = {'results': [{'id': 'page_123'}]}

        # Act
        result = ns.queryNotionEvent_delete()

        # Assert
        self.assertEqual(result, [{'id': 'page_123'}])
        mock_query.assert_called_once()

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_updateGStatus(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {ns.nt.ON_GCAL_NOTION_NAME: {'checkbox': True}}}
        page_id = 'page_123'

        # Act
        result = ns.updateGStatus(page_id)

        # Assert
        self.assertTrue(result['properties'][ns.nt.ON_GCAL_NOTION_NAME]['checkbox'])
        mock_update.assert_called_once_with(page_id=page_id, properties={ns.nt.ON_GCAL_NOTION_NAME: {'checkbox': True}, ns.nt.LASTUPDATEDTIME_NOTION_NAME: {'date': {'start': ns.notion_time(), 'end': None}}})

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_updateDefaultCal(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal_id'}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal'}}]}, ns.nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {'select': {'name': ns.nt.GCAL_DEFAULT_NAME}}}}
        page_id = 'page_123'
        gcal = 'gcal'
        gcal_id = 'gcal_id'

        # Act
        result = ns.updateDefaultCal(page_id, gcal, gcal_id)

        # Assert
        self.assertEqual(result['properties'][ns.nt.GCALEVENTID_NOTION_NAME]['rich_text'][0]['text']['content'], gcal)
        self.assertEqual(result['properties'][ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME]['rich_text'][0]['text']['content'], gcal_id)
        self.assertEqual(result['properties'][ns.nt.CURRENT_CALENDAR_NAME_NOTION_NAME]['select']['name'], ns.nt.GCAL_DEFAULT_NAME)
        mock_update.assert_called_once_with(page_id=page_id, properties={ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal_id}}]}, ns.nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {'select': {'name': ns.nt.GCAL_DEFAULT_NAME}}})

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_updateCal(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal'}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal_id'}}]}}}
        page_id = 'page_123'
        gcal = 'gcal'
        gcal_id = 'gcal_id'

        # Act
        result = ns.updateCal(page_id, gcal, gcal_id)

        # Assert
        self.assertEqual(result['properties'][ns.nt.GCALEVENTID_NOTION_NAME]['rich_text'][0]['text']['content'], gcal)
        self.assertEqual(result['properties'][ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME]['rich_text'][0]['text']['content'], gcal_id)
        mock_update.assert_called_once_with(page_id=page_id, properties={ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal_id}}]}})

    @patch('notion.notion_services.nt.NOTION.pages.update')
    def test_updateNotionTime(self, mock_update):
        # Arrange
        mock_update.return_value = {'id': 'page_123', 'properties': {ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal'}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': 'gcal_id'}}]}, ns.nt.ON_GCAL_NOTION_NAME: {'checkbox': True}}}
        page_id = 'page_123'
        gcal = 'gcal'
        gcal_id = 'gcal_id'
        event = {}

        # Act
        result = ns.updateNotionTime(page_id, gcal, gcal_id, event)

        # Assert
        self.assertTrue(result['properties'][ns.nt.ON_GCAL_NOTION_NAME]['checkbox'])
        mock_update.assert_called_once_with(page_id=page_id, properties={ns.nt.GCALEVENTID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal}}]}, ns.nt.CURRENT_CALENDAR_ID_NOTION_NAME: {'rich_text': [{'text': {'content': gcal_id}}]}, ns.nt.ON_GCAL_NOTION_NAME: {'checkbox': True}, ns.nt.LASTUPDATEDTIME_NOTION_NAME: {'date': {'start': ns.notion_time(), 'end': None}}})

if __name__ == '__main__':
    unittest.main()
