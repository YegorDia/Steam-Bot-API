from Crypto.Cipher import AES
import base64

# the block size for the cipher object; must be 16, 24, or 32 for AES
BLOCK_SIZE = 16

# the character used for padding--with a block cipher such as AES, the value
# you simple_crypto must be a multiple of BLOCK_SIZE in length.  This character is
# used to ensure that your value is always a multiple of BLOCK_SIZE
PADDING = '{'

# one-liner to sufficiently pad the text to be encrypted
pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * PADDING

# one-liners to simple_crypto/encode and decrypt/decode a string
# simple_crypto with AES, encode with base64
EncodeAES = lambda c, s: base64.b64encode(c.encrypt(pad(s)))
DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e)).rstrip(PADDING)


def simple_encode(key, text):
    cipher = AES.new(key)
    encoded = EncodeAES(cipher, text)
    return encoded


def simple_decode(key, text):
    cipher = AES.new(key)
    decoded = DecodeAES(cipher, text)
    return decoded