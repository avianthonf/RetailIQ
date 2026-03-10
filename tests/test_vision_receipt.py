import pytest
from unittest.mock import patch, MagicMock

from app.vision.receipt import ReceiptOCR, digitize_receipt

class TestReceiptOCR:
    @patch('app.vision.receipt.TrOCRProcessor')
    @patch('app.vision.receipt.VisionEncoderDecoderModel')
    def test_init(self, mock_model, mock_processor):
        ocr = ReceiptOCR()
        mock_processor.from_pretrained.assert_called_once_with("microsoft/trocr-small-printed")
        mock_model.from_pretrained.assert_called_once_with("microsoft/trocr-small-printed")

    @patch('app.vision.receipt.TrOCRProcessor')
    @patch('app.vision.receipt.VisionEncoderDecoderModel')
    @patch('app.vision.receipt.Image.open')
    def test_extract_text_success(self, mock_image_open, mock_model, mock_processor):
        ocr = ReceiptOCR()
        mock_image = MagicMock()
        mock_image_open.return_value.convert.return_value = mock_image
        
        mock_processor_instance = mock_processor.from_pretrained.return_value
        mock_processor_instance.return_value.pixel_values = "mock_pixels"
        mock_processor_instance.batch_decode.return_value = ["MOCK TEXt"]
        
        mock_model_instance = mock_model.from_pretrained.return_value
        mock_model_instance.generate.return_value = "mock_generated_ids"

        result = ocr.extract_text("dummy_path.jpg")
        
        assert result == "MOCK TEXt"
        mock_image_open.assert_called_once_with("dummy_path.jpg")
        mock_processor_instance.assert_called_once_with(images=mock_image, return_tensors="pt")
        mock_model_instance.generate.assert_called_once_with("mock_pixels")
        mock_processor_instance.batch_decode.assert_called_once_with("mock_generated_ids", skip_special_tokens=True)

    @patch('app.vision.receipt.TrOCRProcessor')
    @patch('app.vision.receipt.VisionEncoderDecoderModel')
    @patch('app.vision.receipt.Image.open')
    def test_extract_text_exception(self, mock_image_open, mock_model, mock_processor):
        ocr = ReceiptOCR()
        mock_image_open.side_effect = Exception("Failed to open image")
        
        result = ocr.extract_text("dummy_path.jpg")
        
        assert result == "MOCK RECEIPT STORE 101 TOTAL 500.00 ITEMS MILK 2 BREAD 1"

@patch('app.vision.receipt.ReceiptOCR')
@patch('app.vision.parser.parse_invoice_text')
def test_digitize_receipt(mock_parse, mock_ocr_class):
    mock_ocr_instance = mock_ocr_class.return_value
    mock_ocr_instance.extract_text.return_value = "RAW RECEIPT TEXT"
    mock_parse.return_value = [{"name": "MILK", "quantity": 1, "price": 2.5}]
    
    result = digitize_receipt("dummy_path.jpg")
    
    assert result == {
        "raw_text": "RAW RECEIPT TEXT",
        "items": [{"name": "MILK", "quantity": 1, "price": 2.5}]
    }
    mock_ocr_instance.extract_text.assert_called_once_with("dummy_path.jpg")
    mock_parse.assert_called_once_with("RAW RECEIPT TEXT")
