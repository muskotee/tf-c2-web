"""Native TF-C2 clocks: no per-second program/flash uploads.

Templates captured from PowerLED 2.89.4 for this exact TF-C2 firmware.
Only the built-in clock font is enabled after physical display verification.
"""
import datetime as dt
import math
from pathlib import Path
import struct
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from PIL import Image, ImageDraw, ImageFont
import display

ROOT = Path(__file__).resolve().parent / 'clock-templates'
STYLES = {'digital': 'Digital · klassisch', 'segment': 'Börsentafel · gerahmt',
          'binary': 'Binär · BCD-Punkte', 'arcade': 'Arcade · Pac-Man-Ziffern',
          'analog': 'Bahnhof · analog + digital', 'world': 'Weltzeit · zwei Städte'}
SUPPORTED_STYLES = ('digital', 'segment', 'analog', 'world')
ZONES = {'Europe/Berlin': 'Berlin', 'Europe/London': 'London', 'UTC': 'UTC',
         'America/New_York': 'New York', 'Asia/Tokyo': 'Tokio'}
DEFAULT = {'enabled': False, 'style': 'digital', 'content': 'both',
           'color': 'cyan', 'accent': 'amber', 'timezone': 'Europe/Berlin',
           'second_timezone': 'America/New_York', 'date_format': 'de'}


def options(value):
    opt = {k: value.get(k, v) for k, v in DEFAULT.items()}
    if opt['style'] not in STYLES or opt['content'] not in ('time', 'both', 'date'):
        raise ValueError('Unbekannte Uhrdarstellung.')
    if opt['style'] not in SUPPORTED_STYLES:
        raise ValueError('Diese Uhr benötigt eingebettete Schriften, die auf diesem Controller schwarz bleiben. Bitte Digital, Börsentafel, Bahnhof oder Weltzeit wählen.')
    if opt['color'] not in display.COLORS or opt['accent'] not in display.COLORS:
        raise ValueError('Ungültige Uhrfarbe.')
    if opt['date_format'] not in ('de','iso','short'):
        raise ValueError('Ungültiges Datumsformat.')
    for key in ('timezone', 'second_timezone'):
        if opt[key] not in ZONES:
            raise ValueError('Bitte eine angebotene Zeitzone wählen.')
        try:
            ZoneInfo(opt[key])
        except ZoneInfoNotFoundError as exc:
            raise ValueError('Zeitzonendaten fehlen auf dem Raspberry.') from exc
    opt['enabled'] = bool(opt['enabled'])
    if opt['style'] in ('analog', 'world'):
        opt['content'] = 'time'
    return opt


def now(opt, instant=None):
    return (instant or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(opt['timezone']))


def rtc_payload(opt, instant=None):
    # PowerLED command 0x25 stores local wall time as an unsigned Unix-like
    # timestamp, followed by a zero dword. Never send actual UTC for a local RTC.
    local = now(opt, instant).replace(tzinfo=dt.timezone.utc)
    return struct.pack('<II', int(local.timestamp()), 0)


def sync(opt):
    with display.serial_port() as fd:
        info = display.probe_fd(fd)
        reply = display.exchange(fd, display.packet(0x25, rtc_payload(opt), sequence=8))
        if len(reply) != 12 or reply[3:6] != b'\0\0\0':
            raise RuntimeError('Der Controller hat die Uhrzeit nicht bestätigt.')
    return info


def palette(name):
    r, g, b = display.COLORS[name]
    return bool(r) + 2 * bool(b) + 4 * bool(g)


def date_text(opt, current):
    return current.strftime({'de':'%d.%m.%Y','iso':'%Y-%m-%d','short':'%y-%m-%d'}[opt['date_format']])


def windows(program):
    result = []
    for pos in range(348, 528, 12):
        page, x, y, width, height = struct.unpack_from('<IHHHH', program, pos)
        if not page:
            break
        if page + 24 + math.ceil(width / 32) * 4 * height * 3 > len(program):
            raise RuntimeError('Beschädigte native Uhrvorlage.')
        result.append((pos, page, x, y, width, height))
    return result


def font_base(program):
    # Native custom-font magic follows all window rasters.
    end = max(page + 24 + math.ceil(w / 32) * 4 * h * 3 for _, page, _, _, w, h in windows(program))
    if program[end:end+4] != bytes.fromhex('050aa55a'):
        raise RuntimeError('Die native Uhrschrift fehlt.')
    return end


def glyph(program, base, char):
    code = ord(char)
    if not 33 <= code <= 126:
        return Image.new('L', (max(1, struct.unpack_from('<I', program, base+8)[0]), struct.unpack_from('<I', program, base+16)[0]))
    entry = base + 24 + (code - 33) * 8
    offset, width, height = struct.unpack_from('<IHH', program, entry)
    image = Image.new('L', (max(1, width), max(1, height)))
    stride = math.ceil(width / 8)
    for y in range(height):
        for x in range(width):
            if not program[base + offset + y * stride + x // 8] & (1 << (x % 8)):
                image.putpixel((x, y), 255)
    return image


def digit_image(char, width, height, style):
    image = Image.new('L', (width, height)); draw = ImageDraw.Draw(image)
    if style == 'binary' and char.isdigit():
        step = max(2, (height-2)//4)
        for bit in range(4):
            box = (1, 1+bit*step, max(2, width-2), min(height-1, (bit+1)*step-1))
            draw.rectangle(box, fill=255 if int(char) & (8 >> bit) else 0, outline=255)
            if not int(char) & (8 >> bit) and box[2]-box[0] > 2 and box[3]-box[1] > 2:
                draw.rectangle((box[0]+1,box[1]+1,box[2]-1,box[3]-1),fill=0)
    elif style == 'arcade' and char.isdigit():
        font = ImageFont.truetype(display.FONT, max(7, height-8))
        box = font.getbbox(char)
        draw.text(((width-font.getlength(char))//2, height-(box[3]-box[1])-box[1]), char, font=font, fill=255)
        progress = round(int(char) * max(1,width-4) / 9)
        for x in range(progress+4,width,2):draw.point((x,3),fill=255)
        draw.pieslice((progress,1,progress+4,5),30,330,fill=255)
    elif char == ':':
        for cy in (height//3,2*height//3):draw.rectangle((width//2-1,cy-1,width//2,cy),fill=255)
    elif char.isdigit():
        thickness = max(1, width//5); left=1; right=max(left+2,width-2); top=1; mid=height//2; bottom=height-2
        segments = {'0':'ab cdef'.replace(' ',''), '1':'bc','2':'abged','3':'abgcd','4':'fgbc',
                    '5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd'}[char]
        lines={'a':(left,top,right,top),'b':(right,top,right,mid),'c':(right,mid,right,bottom),
               'd':(left,bottom,right,bottom),'e':(left,mid,left,bottom),'f':(left,top,left,mid),'g':(left,mid,right,mid)}
        for name in segments:draw.line(lines[name],fill=255,width=thickness)
    return image


def stylize(program, base, style):
    if style not in ('segment','binary','arcade'):
        return
    for char in '0123456789:':
        entry = base + 24 + (ord(char)-33)*8
        offset, width, height = struct.unpack_from('<IHH',program,entry)
        image = digit_image(char,width,height,style)
        stride = math.ceil(width/8)
        data = bytearray([255]*(stride*height))
        for y in range(height):
            for x in range(width):
                if image.getpixel((x,y)):data[y*stride+x//8] &= ~(1 << (x%8))
        program[base+offset:base+offset+len(data)] = data


def unpack_raster(program, page, width, height):
    image = Image.new('RGB',(width,height)); stride=math.ceil(width/32)*4; plane=stride*height
    for y in range(height):
        for x in range(width):
            image.putpixel((x,y),tuple(255 if program[page+24+c*plane+y*stride+x//8] & (1 << (x%8)) else 0 for c in (0,2,1)))
    return image


def pack_raster(image):
    width,height=image.size;stride=math.ceil(width/32)*4;plane=stride*height;data=bytearray(plane*3)
    for y in range(height):
        for x in range(width):
            pixel=image.getpixel((x,y))
            for c,channel in enumerate((0,2,1)):
                if pixel[channel]>=96:data[c*plane+y*stride+x//8] |= 1 << (x%8)
    return data


def compile_program(value, instant=None):
    opt=options(value)
    kind = opt['style'] if opt['style'] in ('analog','world') else ('compact' if opt['content']=='both' else 'date' if opt['content']=='date' else 'digital')
    program=bytearray((ROOT/(kind+'.bin')).read_bytes())
    # On this physical TF-C2 the unmodified captured custom-font program is
    # black, while the captured built-in font 0 clock is visible and ticking.
    # Use the proven ROM font and omit the unsupported appended font resource.
    program=program[:font_base(program)]
    struct.pack_into('<I', program, 72, 0)  # no appended font-resource directory
    for index,(_,page,x,y,w,h) in enumerate(windows(program)):
        if program[page+7]==11:
            program[page+8] &= 15  # built-in font 0, preserve date/time flags
            program[page+16] = (program[page+16]&0xf0)|1
            for flag,field in ((2,15),(4,16),(8,17)):
                if program[page+8]&flag:
                    program[page+field]=(program[page+field]&15)|(palette(opt['color'])<<4)
            # Native format enum from PowerLED's date-format string table:
            # 1 YYYY-MM-DD, 4 YY-MM-DD, 11 DD.MM.YYYY.
            if program[page+8]&2:
                program[page+15]=(program[page+15]&0xf0)|{'de':11,'iso':1,'short':4}[opt['date_format']]
                program[page+9]=max(0,(w-len(date_text(opt,now(opt,instant)))*6)//2)
            program[page+11]=max(0,(w-48)//2)
        else:
            program[page+15]=program[page+16]=palette(opt['color']);program[page+17]=palette(opt['accent'])
            image=unpack_raster(program,page,w,h)
            image=Image.eval(image.convert('L'),lambda v:255 if v else 0)
            colored=Image.new('RGB',(w,h));colored.paste(display.COLORS[opt['accent']],(0,0,w,h),image)
            program[page+24:page+24+len(pack_raster(colored))]=pack_raster(colored)
        if kind=='world':
            local=now(opt,instant);other=local.astimezone(ZoneInfo(opt['second_timezone']))
            delta=int((other.utcoffset()-local.utcoffset()).total_seconds()/60) if index else 0
            struct.pack_into('<h',program,page+18,delta)
        if opt['style']=='segment':
            image=unpack_raster(program,page,w,h);draw=ImageDraw.Draw(image)
            draw.rectangle((0,0,w-1,h-1),outline=display.COLORS[opt['accent']])
            for xx in range(3,w,4):draw.point((xx,h//2),fill=display.COLORS[opt['accent']])
            data=pack_raster(image);program[page+24:page+24+len(data)]=data
    return bytes(program), opt


def text_mask(program,base,text):
    images=[glyph(program,base,c) for c in text]
    mask=Image.new('L',(sum(im.width for im in images),max(im.height for im in images)))
    x=0
    for image in images:mask.paste(image,(x,0));x+=image.width
    return mask


def preview(value, instant=None):
    program,opt=compile_program(value,instant);local=now(opt,instant)
    canvas=Image.new('RGB',(128,32))
    for index,(_,page,x,y,w,h) in enumerate(windows(program)):
        area=unpack_raster(program,page,w,h)
        if program[page+7]==10:
            d=ImageDraw.Draw(area);cx,cy=w//2,h//2
            for angle,length,color in ((local.hour%12*30+local.minute/2,8,opt['color']),(local.minute*6,12,opt['color']),(local.second*6,13,opt['accent'])):
                radians=math.radians(angle-90);d.line((cx,cy,round(cx+math.cos(radians)*length),round(cy+math.sin(radians)*length)),fill=display.COLORS[color])
        else:
            current=local.astimezone(ZoneInfo(opt['second_timezone'])) if opt['style']=='world' and index else local
            strings=([date_text(opt,current), current.strftime('%H:%M:%S')] if opt['content']=='both'
                     else [date_text(opt,current) if opt['content']=='date' else current.strftime('%H:%M:%S')])
            # Schematic ROM-font preview: firmware draws its own built-in font.
            font=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',10)
            masks=[]
            for text in strings:
                mask=Image.new('L',(len(text)*6,12));draw=ImageDraw.Draw(mask)
                draw.text((0,0),text,font=font,fill=255);masks.append(mask)
            top=max(0,(h-sum(mask.height for mask in masks))//2)
            for mask in masks:
                left=max(0,(w-mask.width)//2)
                colored=Image.new('RGB',mask.size,display.COLORS[opt['color']]);area.paste(colored,(left,top),mask);top+=mask.height
        canvas.paste(area,(x,y))
    return canvas,opt
