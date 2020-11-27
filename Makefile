serve:
	uvicorn event_server:app \
		--host 0.0.0.0 \
		--log-level info \
		--access-log \
		--use-colors \
		--reload \
		--workers 4 \
		--port 1234
