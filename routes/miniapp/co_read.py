from __future__ import annotations

from flask import request


def register_routes(bp) -> None:
    @bp.route("/co-read/session", methods=["POST"])
    def miniapp_co_read_session():
        from routes.co_read_api import handle_co_read_session

        return handle_co_read_session()

    @bp.route("/co-read/books", methods=["GET", "POST"])
    def miniapp_co_read_books():
        from routes.co_read_api import handle_co_read_books

        return handle_co_read_books()

    @bp.route("/co-read/uploads", methods=["POST"])
    def miniapp_co_read_upload_start():
        from routes.co_read_api import handle_co_read_upload_start

        return handle_co_read_upload_start()

    @bp.route("/co-read/uploads/<upload_id>/chunks", methods=["POST"])
    def miniapp_co_read_upload_chunk(upload_id: str):
        from routes.co_read_api import handle_co_read_upload_chunk

        return handle_co_read_upload_chunk(upload_id)

    @bp.route("/co-read/uploads/<upload_id>/finish", methods=["POST"])
    def miniapp_co_read_upload_finish(upload_id: str):
        from routes.co_read_api import handle_co_read_upload_finish

        return handle_co_read_upload_finish(upload_id)

    @bp.route("/co-read/books/<book_key>", methods=["GET", "DELETE"])
    def miniapp_co_read_book_detail(book_key: str):
        from routes.co_read_api import handle_co_read_book_delete, handle_co_read_book_detail

        if request.method == "DELETE":
            return handle_co_read_book_delete(book_key)
        return handle_co_read_book_detail(book_key)

    @bp.route("/co-read/books/<book_key>/sections/<section_id>", methods=["PUT"])
    def miniapp_co_read_section_update(book_key: str, section_id: str):
        from routes.co_read_api import handle_co_read_section_update

        return handle_co_read_section_update(book_key, section_id)

    @bp.route("/co-read/books/<book_key>/sections/<section_id>/complete", methods=["POST"])
    def miniapp_co_read_section_complete(book_key: str, section_id: str):
        from routes.co_read_api import handle_co_read_section_complete

        return handle_co_read_section_complete(book_key, section_id)
