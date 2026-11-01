import datetime as dt
import struct
import threading
import unittest
from unittest import mock
import clocks
import display
import server


class ClockTests(unittest.TestCase):
    def test_all_styles_and_contents_compile_with_native_clock_headers(self):
        for style in clocks.STYLES:
            for content in ('time','both','date'):
                with self.subTest(style=style,content=content):
                    program,opt=clocks.compile_program({'style':style,'content':content})
                    windows=clocks.windows(program)
                    self.assertTrue(windows)
                    self.assertTrue(all(program[p+7] in (10,11) for _,p,*_ in windows))
                    base=clocks.font_base(program)
                    self.assertEqual(program[base:base+4],bytes.fromhex('050aa55a'))
                    image,_=clocks.preview(opt)
                    self.assertEqual(image.size,(128,32))
                    self.assertIsNotNone(image.getbbox())

    def test_native_fonts_change_pixels_without_moving_any_pointers(self):
        reference,_=clocks.compile_program({'style':'digital','content':'time'})
        for style in ('segment','binary','arcade'):
            program,_=clocks.compile_program({'style':style,'content':'time'})
            base=clocks.font_base(program)
            self.assertEqual(len(program),len(reference))
            self.assertEqual(program[base:base+1064],reference[base:base+1064])
            self.assertNotEqual(clocks.glyph(program,base,'9').tobytes(),clocks.glyph(reference,base,'9').tobytes())

    def test_local_rtc_payload_and_dst(self):
        instant=dt.datetime(2026,7,1,12,0,tzinfo=dt.timezone.utc)
        stamp,reserved=struct.unpack('<II',clocks.rtc_payload(clocks.options({}),instant))
        self.assertEqual(dt.datetime.fromtimestamp(stamp,dt.timezone.utc).hour,14)
        self.assertEqual(reserved,0)
        winter=instant.replace(month=1)
        stamp,_=struct.unpack('<II',clocks.rtc_payload(clocks.options({}),winter))
        self.assertEqual(dt.datetime.fromtimestamp(stamp,dt.timezone.utc).hour,13)

    def test_world_clock_offset_tracks_different_dst_dates(self):
        for month,day,delta in ((1,15,-360),(3,20,-300),(7,15,-360)):
            instant=dt.datetime(2026,month,day,12,tzinfo=dt.timezone.utc)
            program,_=clocks.compile_program({'style':'world'},instant)
            page=clocks.windows(program)[1][1]
            self.assertEqual(struct.unpack_from('<h',program,page+18)[0],delta)

    def test_reject_invalid_settings(self):
        for value in ({'style':'random'},{'timezone':'Mars/Olympus'},{'content':'video'},{'color':'pink'}):
            with self.assertRaises(ValueError):clocks.options(value)

    def test_date_formats_use_native_enum_and_center_actual_glyph_width(self):
        instant=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
        for fmt,code,text in (('de',11,'01.11.2026'),('iso',1,'2026-11-01'),('short',4,'26-11-01')):
            program,opt=clocks.compile_program({'content':'date','date_format':fmt},instant)
            page=clocks.windows(program)[0][1];base=clocks.font_base(program)
            self.assertEqual(program[page+15]&15,code)
            self.assertEqual(clocks.date_text(opt,clocks.now(opt,instant)),text)
            self.assertEqual(program[page+9],(128-clocks.text_mask(program,base,text).width)//2)

    def test_sync_only_sends_captured_rtc_command(self):
        with mock.patch.object(display,'serial_port') as port,mock.patch.object(display,'probe_fd',return_value={'connected':True}),mock.patch.object(display,'exchange',return_value=bytes.fromhex('0c000a000000010000051c00')) as exchange:
            port.return_value.__enter__.return_value=123
            clocks.sync(clocks.options({}))
            data=bytearray(exchange.call_args.args[1]);key=data[2]
            for i in range(len(data)):
                if i!=2:data[i]^=((i+1+key) if i%2 else (i+5)*key)&255
            self.assertEqual(data[3],0x25)
            self.assertEqual(len(data[8:-4]),8)

    def test_clock_updates_do_not_reupload_or_overwrite_restore_point(self):
        saved={'last':{'source':'text','options':{'text':'Original'}},'auto':{'enabled':True},'clock':{}}
        control=server.Controller.__new__(server.Controller)
        control.lock=threading.Lock();control.hardware_lock=threading.Lock();control.device={};control.update=mock.Mock()
        result={'pages':1,'options':{'text':'Uhr'},'bytes':100}
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(display,'upload_program',return_value=result) as upload,mock.patch.object(clocks,'sync',return_value={'connected':True}):
            control.clock_job('clock',{})
            restore=saved['clock_previous']
            control.clock_job('clock_sync',{})
            control.clock_job('clock_sync',{})
            self.assertEqual(upload.call_count,1)
            self.assertEqual(saved['clock_previous'],restore)
            self.assertEqual(restore['last']['options']['text'],'Original')
            self.assertFalse(saved['auto']['enabled'])
            self.assertTrue(saved['clock']['enabled'])


if __name__=='__main__':unittest.main()
