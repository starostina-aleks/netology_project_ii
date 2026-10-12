import tiktoken
from langchain_text_splitters import  RecursiveCharacterTextSplitter,MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from datetime import datetime, timezone, timedelta

# Функция подсчета токенов для модели эмбеддингов
def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


# Функция разделения текста на чанки заданной длины (в токенах)
def split_text_fragment(text, max_count, chunk_overlap):
    # Функция для подсчета количества токенов во фрагменте для сплиттера RecursiveCharacterTextSplitter
    def num_tokens(fragment):
        return num_tokens_from_string(fragment, "cl100k_base")

    num_levels = 3  # Число уровней заголовков, которые будем разделять сплиттером MarkdownHeaderTextSplitter
    headers_to_split_on = [
        (f"{'#' * i}", f"H{i}") for i in range(1, num_levels + 1)
    ]

    # сначала разделим с помощью MarkdownHeaderTextSplitter
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
    fragments = markdown_splitter.split_text(text)
    return fragments


# Функция разделения текста на чанки заданной длины (в токенах)
def split_text(text, data_info, max_count, chunk_overlap):
    # Функция для подсчета количества токенов во фрагменте для сплиттера RecursiveCharacterTextSplitter
    def num_tokens(fragment):
        return num_tokens_from_string(fragment, "cl100k_base")

    num_levels = 3  # Число уровней заголовков, которые будем разделять сплиттером MarkdownHeaderTextSplitter
    headers_to_split_on = [
        (f"{'#' * i}", f"H{i}") for i in range(1, num_levels + 1)
    ]

    # сначала разделим с помощью MarkdownHeaderTextSplitter
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
    fragments = markdown_splitter.split_text(text)

    # дальше будем делить делить каждый полученный чанк вторым сплиттером RecursiveCharacterTextSplitter
    # 1. для того, чтобы быть уверенным в размере полученного чанка
    # 2. база знаний размечена так, что заголовки не повторяются в тексте разделов, мы это исправим принудительно:

    splitter = RecursiveCharacterTextSplitter(chunk_size=max_count, chunk_overlap=chunk_overlap,
                                              length_function=num_tokens)

    source_chunks = []

    now_iso = datetime.now(timezone.utc).isoformat()
    start=0
    # Обработаем каждый фрагмент текста, полученный после MarkdownHeaderTextSplitter
    for fragment in fragments:
        #if len(fragment.metadata)==1:
        # MarkdownHeaderTextSplitter сохранил иерархию заголовков в Метаданных - вытащим ее
        level = 0

        headers = ['', '', '', '']
        for j in range(1, num_levels + 1):
            header_key = f'H{j}'
            if header_key in fragment.metadata: level, headers[j - 1] = j, fragment.metadata[header_key]
        header_string = ' '.join([f"{'#' * i} {header}" for i, header in enumerate(headers[:level], start=1)])

        # каждый фрагмент будем разбивать на чанки с помощью RecursiveCharacterTextSplitter
        # допишем иерархию заголовков в конец чанка
        # унаследуем метаданные от первого сплиттера
        # добавим в метаданные размер чанка в токенах
        for i, chunk in enumerate(splitter.split_text(fragment.page_content)):
            if start==0:
                start = 1
                tenant_id=1
            else:
                start=0
                tenant_id=2
            date_obj = datetime.now(timezone.utc).date() - timedelta(days=start)
            now_iso = f"{date_obj.isoformat()}T00:00:00Z"

            mdata = fragment.metadata.copy()
            add_hierarchy = f'{header_string}: уровень {level} пункт {i + 1}'
            #new_chunk = ' '.join([chunk, f'\nРаздел: {add_hierarchy}'])
            #mdata["len"] = num_tokens(new_chunk)
            mdata["len"] = num_tokens(chunk)
            mdata["source"]=data_info["source"]
            mdata["hierarchy"] = add_hierarchy
            mdata["category"] = headers[0].split('.')[0]
            mdata["created_at"] = now_iso
            mdata["tenant_id"]=tenant_id

            #doc = Document(page_content=new_chunk, metadata=mdata)
            doc = Document(page_content=chunk, metadata=mdata)
            source_chunks.append(doc)

    print(now_iso)
    return source_chunks

def prepare_docs():
    file_ustav_txt='data/Korabelny_ustav_VMF_2022.txt'

    with open(file_ustav_txt, "r", encoding="utf-8") as file:
        # Читаем содержимое файла
        content = file.read()

    chunk_size=512
    chunk_overlap=84
    data_info={
        "source": "Korabelny_ustav_VMF_2022.txt",
    }
    docs = split_text(content,data_info,chunk_size, chunk_overlap)

    return docs

prepare_docs()