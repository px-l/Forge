import base64
import struct
import pytest
from backend.design import design_viewport
from backend.sample import SAMPLE_TARGET


def png_header(w,h):
    return 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',w,h)).decode()


def test_generated_reference_dimensions():
    image=png_header(1664,928)
    assert design_viewport(image)=={'width':1664,'height':928}
    assert image==png_header(1664,928)  # baseline bytes are untouched


def test_fallback_and_demo_dimensions():
    assert design_viewport(None)=={'width':1440,'height':900}
    assert design_viewport(SAMPLE_TARGET)=={'width':1440,'height':900}


@pytest.mark.parametrize('value',[png_header(0,900),png_header(3000,900),'data:image/png;base64,broken'])
def test_invalid_reference_is_not_silently_resized(value):
    with pytest.raises(ValueError):design_viewport(value)
