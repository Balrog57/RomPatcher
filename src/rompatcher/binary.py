from __future__ import annotations


class BinaryReader:
    def __init__(self, data: bytes | bytearray | memoryview):
        self._data = memoryview(data)
        self._pos = 0

    @property
    def size(self) -> int:
        return len(self._data)

    def tell(self) -> int:
        return self._pos

    def seek(self, position: int) -> None:
        if position < 0 or position > self.size:
            raise ValueError(f"Invalid seek position: {position}")
        self._pos = position

    def skip(self, amount: int) -> None:
        self.seek(self._pos + amount)

    def remaining(self) -> int:
        return self.size - self._pos

    def eof(self) -> bool:
        return self._pos >= self.size

    def require(self, count: int) -> None:
        if self._pos + count > self.size:
            raise ValueError("Unexpected end of file")

    def peek_bytes(self, count: int) -> bytes:
        self.require(count)
        return self._data[self._pos : self._pos + count].tobytes()

    def read_bytes(self, count: int) -> bytes:
        data = self.peek_bytes(count)
        self._pos += count
        return data

    def read_text(self, count: int, encoding: str = "latin-1") -> str:
        return self.read_bytes(count).decode(encoding, errors="replace")

    def read_u8(self) -> int:
        self.require(1)
        value = self._data[self._pos]
        self._pos += 1
        return int(value)

    def read_u16_be(self) -> int:
        return int.from_bytes(self.read_bytes(2), "big")

    def read_u16_le(self) -> int:
        return int.from_bytes(self.read_bytes(2), "little")

    def read_u24_be(self) -> int:
        return int.from_bytes(self.read_bytes(3), "big")

    def read_u32_be(self) -> int:
        return int.from_bytes(self.read_bytes(4), "big")

    def read_u32_le(self) -> int:
        return int.from_bytes(self.read_bytes(4), "little")

    def read_u64_le(self) -> int:
        return int.from_bytes(self.read_bytes(8), "little")
