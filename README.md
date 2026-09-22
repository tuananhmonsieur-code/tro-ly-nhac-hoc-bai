# Trợ lý học tập local

Ứng dụng có web local để hỏi bài bằng văn bản hoặc ảnh đề bài. Gemini 3.6 Flash xử lý multimodal và trả lời theo hướng gia sư học thuật; SQLite và scheduler hiện tại vẫn dùng cho lịch nhắc desktop.

## Chạy web

1. Tạo môi trường và cài dependency:

	```powershell
	.venv\Scripts\python.exe -m pip install -r requirements.txt
	```

2. Sao chép `.env.example` thành `.env`, rồi điền `GEMINI_API_KEY`.

3. Khởi động:

	```powershell
	.venv\Scripts\python.exe web_app.py
	```

4. Mở http://127.0.0.1:5000.

Ảnh được nhận ở định dạng JPG, PNG hoặc WEBP, tối đa 8 MB. Không đưa `.env` hoặc API key vào Git.
