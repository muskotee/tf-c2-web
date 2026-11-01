import datetime as dt
import struct
import threading
import unittest
import tempfile
from pathlib import Path
from PIL import Image
from unittest import mock
import clocks
import display
import server


class ClockTests(unittest.TestCase):
    def test_date_uses_native_clock_character_pitch_and_single_pixel_strokes(self):
        program,_=clocks.compile_program({'style':'analog','color':'red'})
        _,page,_,_,w,h=clocks.windows(program)[2]
        image=clocks.unpack_raster(program,page,w,h)
        bounds=image.getbbox()
        self.assertEqual(bounds[3]-bounds[1],7)
        self.assertLessEqual(bounds[2]-bounds[0],10*6)
        self.assertGreater(bounds[2]-bounds[0],8*6)
        self.assertLessEqual(abs(bounds[1]-(h-bounds[3])),1)

    def test_clock_logo_left_and_right_reserve_aligned_nonoverlapping_slots(self):
        identifier='a'*64
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(clocks.logos,'ROOT',Path(folder)):
            Image.new('RGBA',(40,20),(255,0,0,255)).save(Path(folder)/(identifier+'.png'))
            for style in ('digital','analog'):
                for side in ('left','right'):
                    value={'style':style,'content':'both','logo_id':identifier,'logo_position':side}
                    program,_=clocks.compile_program(value)
                    areas=clocks.windows(program)
                    logo=areas[-1]
                    self.assertEqual(logo[2:],(32 if style=='analog' and side=='left' else 0 if side=='left' else 96,0,32,32))
                    native=next(a for a in areas if program[a[1]+7]==11)
                    self.assertEqual(native[4],64 if style=='analog' else 96)
                    for index,a in enumerate(areas):
                        self.assertEqual(a[2]%32,0)
                        for b in areas[index+1:]:
                            self.assertTrue(a[2]+a[4]<=b[2] or b[2]+b[4]<=a[2] or a[3]+a[5]<=b[3] or b[3]+b[5]<=a[3])
                    preview,_=clocks.preview(value)
                    self.assertEqual(preview.size,(128,32))
            with self.assertRaisesRegex(ValueError,'beide Displayhälften'):
                clocks.options({'style':'world','logo_id':identifier})

    def test_calendar_day_only_changes_the_date_raster(self):
        instant=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
        a,_=clocks.compile_program({'style':'analog'},instant)
        b,_=clocks.compile_program({'style':'analog'},instant.replace(day=2))
        footer=clocks.windows(a)[2][1]
        self.assertEqual(a[:footer+24],b[:footer+24])
        self.assertNotEqual(a[footer+24:],b[footer+24:])

    def test_existing_station_clock_is_reuploaded_after_layout_update(self):
        saved={'clock':{'enabled':True,'style':'analog','content':'time','engine':2}}
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(threading.Thread,'start'):
            control=server.Controller()
            _,kind,value=control.jobs.get_nowait()
            self.assertEqual((kind,value['style']),('clock','analog'))

    def test_station_viewports_are_aligned_centered_and_have_exact_raster_sizes(self):
        program,_=clocks.compile_program({'style':'analog'})
        first,second,third=clocks.windows(program)
        self.assertEqual(first[2:],(0,0,32,32))
        self.assertEqual(second[2:],(32,4,96,12))
        self.assertEqual(third[2:],(32,19,96,10))
        _,page,x,y,width,height=second
        self.assertEqual(x%32,0)
        self.assertEqual(width%32,0)
        self.assertLess(y+height,third[3])
        self.assertLessEqual(third[3]+third[5],32)
        left=program[page+11]
        self.assertEqual(left,width-(left+48))
        self.assertEqual(page,first[1]+24+32*32*3//8)
        self.assertEqual(third[1],page+24+96*12*3//8)
        self.assertEqual(len(program),third[1]+24+96*10*3//8)
        self.assertFalse(any(program[page+24:third[1]]))
        self.assertTrue(any(program[third[1]+24:]))
        self.assertEqual(program[page+8]&15,8)
        self.assertEqual(program[third[1]+7],2)
        self.assertEqual(struct.unpack_from('<I',program,72)[0],0)

    def test_station_preserves_visibly_verified_hand_parameters_for_all_colors(self):
        reference=(clocks.ROOT/'analog.bin').read_bytes()[576:600]
        for color in display.COLORS:
            program,_=clocks.compile_program({'style':'analog','color':color,'accent':color})
            self.assertEqual(program[576:600],reference)

    def test_old_active_clock_is_migrated_to_compatible_renderer(self):
        saved={'clock':{'enabled':True,'style':'binary','content':'time'},'clock_previous':{'last':{'source':'timeline'}}}
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(threading.Thread,'start'):
            control=server.Controller()
            _,kind,value=control.jobs.get_nowait()
            self.assertEqual(kind,'clock')
            self.assertEqual(value['style'],'digital')
            self.assertFalse(saved['clock']['enabled'])
            self.assertEqual(saved['clock_previous']['last']['source'],'timeline')

    def test_native_time_preserves_working_header_and_has_no_external_font(self):
        program,_=clocks.compile_program({'style':'digital','content':'time','color':'red'})
        self.assertEqual(program[576:600],(clocks.ROOT/'standard.bin').read_bytes()[576:600])
        self.assertEqual(clocks.windows(program)[0][2:],(0,10,128,12))
        self.assertEqual(struct.unpack_from('<I',program,72)[0],0)
        self.assertFalse(any(program[600:]))

    def test_all_styles_and_contents_compile_with_native_clock_headers(self):
        for style in clocks.SUPPORTED_STYLES:
            for content in ('time','both','date'):
                with self.subTest(style=style,content=content):
                    program,opt=clocks.compile_program({'style':style,'content':content})
                    windows=clocks.windows(program)
                    self.assertTrue(windows)
                    self.assertTrue(all(program[p+7] in (2,10,11) for _,p,*_ in windows))
                    end=max(p+24+((w+31)//32)*4*h*3 for _,p,_,_,w,h in windows)
                    self.assertEqual(len(program),end)
                    for _,p,*_ in windows:
                        if program[p+7]==11:
                            self.assertEqual(program[p+8]>>4,0)
                            self.assertEqual(program[p+16]&15,1)
                    image,_=clocks.preview(opt)
                    self.assertEqual(image.size,(128,32))
                    self.assertIsNotNone(image.getbbox())

    def test_embedded_font_styles_are_rejected_instead_of_displaying_black(self):
        for style in ('binary','arcade'):
            with self.assertRaisesRegex(ValueError,'eingebettete Schriften'):
                clocks.compile_program({'style':style})

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

    def test_date_formats_render_exact_strings_and_center_visible_pixels(self):
        instant=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
        for fmt,code,text in (('de',11,'01.11.2026'),('iso',1,'2026-11-01'),('short',4,'26-11-01')):
            program,opt=clocks.compile_program({'content':'date','date_format':fmt},instant)
            page=clocks.windows(program)[0][1]
            self.assertEqual(program[page+7],2)
            self.assertEqual(clocks.date_text(opt,clocks.now(opt,instant)),text)
            actual=clocks.unpack_raster(program,page,128,32)
            expected=clocks.centered_text(text,128,32,display.COLORS[opt['color']])
            self.assertEqual(actual.tobytes(),expected.tobytes())
            bounds=actual.getbbox()
            self.assertLessEqual(abs(bounds[1]-(32-bounds[3])),1)

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

    def test_old_date_rebuilds_once_and_keeps_restore_point(self):
        saved={'last':{'source':'text','options':{'text':'Original'}},'auto':{'enabled':False},'clock':{}}
        control=server.Controller.__new__(server.Controller)
        control.lock=threading.Lock();control.hardware_lock=threading.Lock();control.device={};control.update=mock.Mock()
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(display,'upload_program',side_effect=lambda p,r,*args:r) as upload,mock.patch.object(clocks,'sync',return_value={'connected':True}):
            control.clock_job('clock',{'style':'analog'})
            restore=saved['clock_previous']
            saved['clock']['date_day']='2000-01-01'
            control.clock_job('clock_sync',{})
            control.clock_job('clock_sync',{})
            self.assertEqual(upload.call_count,2)
            self.assertEqual(saved['clock']['date_day'],clocks.now(clocks.options({})).date().isoformat())
            self.assertEqual(saved['clock_previous'],restore)


if __name__=='__main__':unittest.main()
