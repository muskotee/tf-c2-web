import datetime as dt
import struct
import unittest
from unittest import mock
import display
import clocks
import programs
import server
import threading


class ProgramTests(unittest.TestCase):
    def test_timeline_time_sync_does_not_upload_again_without_calendar_change(self):
        project={'name':'Test','scenes':[{'id':'c','type':'clock','options':{'style':'analog','duration':5}}]}
        _,result=display.compile_timeline(project)
        saved={}
        control=server.Controller.__new__(server.Controller)
        control.lock=threading.Lock();control.hardware_lock=threading.Lock();control.device={};control.update=mock.Mock()
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(clocks,'sync',return_value={'connected':True}) as sync,mock.patch.object(display,'upload',return_value=result) as upload:
            control.enable_timeline_clock(result)
            control.timeline_sync();control.timeline_sync()
            upload.assert_not_called();self.assertEqual(sync.call_count,2)
            saved['timeline_clock']['signature']=[]
            control.timeline_sync()
            upload.assert_called_once()
            self.assertEqual(saved['last']['source'],'timeline')
            self.assertTrue(saved['timeline_clock']['enabled'])

    def test_stopping_standalone_clock_restores_clock_timeline_and_maintenance(self):
        project={'name':'Wiederherstellen','scenes':[{'id':'c','type':'clock','options':{}}]}
        _,result=display.compile_timeline(project)
        saved={'clock_previous':{'last':{'source':'timeline',**result},'auto':{'enabled':False}}}
        control=server.Controller.__new__(server.Controller)
        control.lock=threading.Lock();control.hardware_lock=threading.Lock();control.device={};control.update=mock.Mock()
        with mock.patch.object(server,'setting',side_effect=lambda k,d=None:saved.get(k,d)),mock.patch.object(server,'save_setting',side_effect=lambda k,v:saved.__setitem__(k,v)),mock.patch.object(clocks,'sync',return_value={'connected':True}),mock.patch.object(display,'upload',return_value=result):
            control.clock_job('clock_stop',{})
            self.assertTrue(saved['timeline_clock']['enabled'])
            self.assertFalse(saved['clock']['enabled'])
            self.assertEqual(saved['last']['name'],'Wiederherstellen')

    def test_directory_reproduces_native_powerled_two_and_three_program_captures(self):
        source=(clocks.ROOT/'playlist-single.bin').read_bytes()
        for times,filename in (((5,7),'playlist-two.bin'),((5,7,9),'playlist-three.bin')):
            with self.subTest(times=times):
                self.assertEqual(programs.merge([(source,t) for t in times]),(clocks.ROOT/filename).read_bytes())

    def test_text_clock_text_keeps_types_durations_and_rebases_native_windows(self):
        value={'scenes':[{'id':'a','options':{'text':'A','duration':2}},
                         {'id':'c','type':'clock','options':{'style':'analog','duration':7}},
                         {'id':'b','options':{'text':'B','duration':3}}]}
        data,result=display.compile_timeline(value)
        self.assertTrue(result['has_clock'])
        self.assertEqual([s['type'] for s in result['scenes']],['text','clock','text'])
        self.assertEqual(struct.unpack_from('<H',data,120)[0],3)
        for index,seconds in enumerate((2,7,3)):
            start=struct.unpack_from('<I',data,128+index*4)[0]
            self.assertEqual(struct.unpack_from('<HB',data,start),(seconds,1 if index==1 else 0))
            page=struct.unpack_from('<I',data,start+216)[0]
            self.assertGreaterEqual(page,start+444)
            self.assertEqual(data[page+7],10 if index==1 else 2)
        start=struct.unpack_from('<I',data,132)[0]
        self.assertEqual([data[struct.unpack_from('<I',data,start+216+i*12)[0]+7] for i in range(3)],[10,11,2])

    def test_scene_timezone_offsets_are_relative_to_one_rtc(self):
        scenes=[{'id':'berlin','type':'clock','options':{'timezone':'Europe/Berlin','content':'time'}},
                {'id':'tokyo','type':'clock','options':{'timezone':'Asia/Tokyo','content':'time'}}]
        data,_=display.compile_timeline({'scenes':scenes})
        start=struct.unpack_from('<I',data,132)[0]
        page=struct.unpack_from('<I',data,start+216)[0]
        expected=int((clocks.now(clocks.options({'timezone':'Asia/Tokyo'})).utcoffset()-clocks.now(clocks.options({})).utcoffset()).total_seconds()/60)
        self.assertEqual(struct.unpack_from('<h',data,page+18)[0],expected)

    def test_clock_scene_cannot_be_saved_with_invalid_duration_or_unknown_style(self):
        for opt in ({'duration':1},{'style':'arcade'}):
            with self.assertRaises(ValueError):display.timeline_project({'scenes':[{'id':'bad','type':'clock','options':opt}]})

    def test_daily_signature_does_not_change_for_seconds_but_does_at_local_midnight(self):
        value={'scenes':[{'id':'a','type':'clock','options':{'timezone':'Europe/Berlin'}}]}
        instant=dt.datetime(2026,11,1,22,59,tzinfo=dt.timezone.utc)
        before=display.timeline_clock_signature(value,instant)
        self.assertEqual(before,display.timeline_clock_signature(value,instant.replace(second=20)))
        self.assertNotEqual(before,display.timeline_clock_signature(value,instant+dt.timedelta(minutes=1)))


if __name__=='__main__':unittest.main()
