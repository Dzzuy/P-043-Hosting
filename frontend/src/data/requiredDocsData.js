import { REQUIRED_VEHICLE_PDFS } from './vehicleData';
import { REQUIRED_POLICY_PDFS } from './policyData';
import { REQUIRED_FEE_PDFS } from './feeData';
import { REQUIRED_FAQ_PDFS } from './faqData';

export const REQUIRED_DOC_CATEGORIES = [
  {
    key: 'vehicles',
    name: 'Thông tin xe & Thông số kỹ thuật',
    icon: 'car',
    count: REQUIRED_VEHICLE_PDFS.length,
    description: 'Các tệp PDF thông số kỹ thuật chi tiết, kích thước, pin, động cơ và trang bị của 7 dòng xe điện VinFast.',
    items: REQUIRED_VEHICLE_PDFS,
  },
  {
    key: 'policies',
    name: 'Chính sách bán hàng & Hợp đồng',
    icon: 'policy',
    count: REQUIRED_POLICY_PDFS.length,
    description: 'Các tệp PDF hợp đồng mua bán xe, hợp đồng cho thuê pin, điều khoản đặt cọc và chính sách khuyến mại.',
    items: REQUIRED_POLICY_PDFS,
  },
  {
    key: 'fees',
    name: 'Biểu phí & Bảng giá niêm yết',
    icon: 'fee',
    count: REQUIRED_FEE_PDFS.length,
    description: 'Các tệp PDF bảng giá xe niêm yết, biểu phí gói thuê pin hàng tháng và bảng giá dịch vụ trạm sạc V-GREEN.',
    items: REQUIRED_FEE_PDFS,
  },
  {
    key: 'faq',
    name: 'Câu hỏi thường gặp FAQ',
    icon: 'faq',
    count: REQUIRED_FAQ_PDFS.length,
    description: 'Các tệp PDF giải đáp thắc mắc chuyên sâu cho từng dòng xe (VF 3 - VF 9) phục vụ tư vấn viên.',
    items: REQUIRED_FAQ_PDFS,
  },
];

export const TOTAL_REQUIRED_PDFS =
  REQUIRED_VEHICLE_PDFS.length +
  REQUIRED_POLICY_PDFS.length +
  REQUIRED_FEE_PDFS.length +
  REQUIRED_FAQ_PDFS.length;

export const INGESTION_GUIDE = {
  storage_directory: 'data/knowledge/',
  corpus_file: 'data/knowledge/corpus.json',
  faq_file: 'data/knowledge/faq.json',
  supported_formats: ['PDF (.pdf, text-searchable / OCR)', 'Markdown / TXT (.md, .txt)', 'JSON cấu trúc chuẩn'],
  ingestion_command: 'python scripts/ingestion/build_corpus.py --product-zip <path_to_product.zip> --knowledge-zip <path_to_knowledge.zip>',
  api_endpoint: '/api/v1/copilot/ingest',
};
