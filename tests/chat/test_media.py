import pytest
from app.chat.media import media_to_part
from pypdf import PdfWriter
from unittest.mock import AsyncMock, MagicMock
import base64


class FakeUploadFile:
    def __init__(self,
                 content_type:str,
                 data:bytes,
                 filename:str="file"):
        self.content_type = content_type
        self._data = data
        self.size=len(data)
        self.filename = filename

    async def read(self)->bytes:
        return self._data

@pytest.mark.asyncio
async def test_media_to_part(tmp_path):
    writer=PdfWriter()
    writer.add_blank_page(width=72,height=72)
    pdf_path=tmp_path / "test.pdf"
    with open(pdf_path,"wb") as fp:
        writer.write(fp)

    data=pdf_path.read_bytes()
    f=FakeUploadFile(content_type="application/pdf",data=data,filename="test.pdf")
    llm=MagicMock()
    part=await media_to_part(f,llm)
    assert part["type"]=="text"
    assert "[Документ PDF]" in part["text"]

@pytest.mark.asyncio
async def test_image_to_return_base64_data_url():
    data=b"abc"
    f=FakeUploadFile(content_type="image/png",data=data,filename="test.png")
    llm=MagicMock()
    part=await media_to_part(f,llm)
    assert part["type"]=="image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")
    b64 = part["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(b64) == data

@pytest.mark.asyncio
async def test_audio_to_part_calls_whisper():
    data=b"abc"
    f=FakeUploadFile(content_type="audio/ogg",data=data,filename="test.ogg")
    llm=MagicMock()
    llm.audio.transcriptions.create=AsyncMock(
        return_value=MagicMock(text="Привет!")
    )
    part=await media_to_part(f,llm)
    assert part["type"]=="text"
    assert "Пользователь сказал голосом" in part["text"]
    assert "Привет!" in part["text"]
    llm.audio.transcriptions.create.assert_awaited_once()
