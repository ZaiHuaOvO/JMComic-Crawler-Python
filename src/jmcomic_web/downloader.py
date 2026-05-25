from __future__ import annotations

from typing import Callable, Optional

from jmcomic import JmAlbumDetail, JmDownloader, JmImageDetail, JmPhotoDetail, jm_log


class WebProgressDownloader(JmDownloader):
    """只在新 Web 层使用的下载器包装。

    不修改原有下载逻辑，只通过回调把进度抛给管理器。
    """

    def __init__(self, option, progress_callback: Optional[Callable[..., None]] = None):
        super().__init__(option)
        self.progress_callback = progress_callback

    def _emit(self, event: str, **payload):
        if self.progress_callback is None:
            return

        try:
            self.progress_callback(event, **payload)
        except Exception as exc:
            jm_log("web.progress", f"进度回调失败: {exc}", exc)

    def before_album(self, album: JmAlbumDetail):
        super().before_album(album)
        self._emit("album_start", album=album, photo_total=len(album))

    def after_photo(self, photo: JmPhotoDetail):
        super().after_photo(photo)
        self._emit(
            "photo_done",
            photo=photo,
            photo_index=photo.album_index,
            photo_total=len(photo.from_album) if photo.from_album is not None else 0,
            image_total=len(photo),
        )

    def after_image(self, image: JmImageDetail, img_save_path):
        super().after_image(image, img_save_path)
        self._emit(
            "image_done",
            image=image,
            img_save_path=img_save_path,
        )

    def after_album(self, album: JmAlbumDetail):
        super().after_album(album)
        self._emit("album_done", album=album, photo_total=len(album))

