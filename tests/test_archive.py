"""write_archive(): fixed metadata, naming and cleanup, checked member by member."""
import gzip
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mindslice.baking.archive import archive_format, write_archive
from mindslice.operations.gc import TEMP_SLICE


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mindslice-archive-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.tree = self.tmp / 'tree'
        (self.tree / 'topic').mkdir(parents=True)
        (self.tree / 'slice.toml').write_text('name = "notes"\n')
        (self.tree / 'topic' / 'note.md').write_bytes(b'# Note\n')

    def test_format_follows_the_suffix_in_any_case(self):
        for name, fmt in (('a.zip', 'zip'), ('A.ZIP', 'zip'), ('a.tar.gz', 'tar.gz'), ('a.TGZ', 'tar.gz'),
                          ('a.slice', 'directory'), ('a.tar', 'directory'), ('zip', 'directory')):
            self.assertEqual(archive_format(Path(name)), fmt, name)

    def test_zip_members(self):
        output = self.tmp / 'out' / 'notes.zip'
        write_archive(self.tree, output, 'zip')
        with zipfile.ZipFile(output) as archive:
            infos = {i.filename: i for i in archive.infolist()}
            self.assertEqual(list(infos), ['notes.slice/', 'notes.slice/slice.toml', 'notes.slice/topic/',
                                           'notes.slice/topic/note.md'])
            for name, info in infos.items():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0), name)
                directory = name.endswith('/')
                self.assertEqual(info.external_attr, ((0o40755 << 16) | 0x10) if directory else 0o100644 << 16, name)
                self.assertEqual(info.is_dir(), directory, name)
            self.assertEqual(infos['notes.slice/topic/note.md'].compress_type, zipfile.ZIP_DEFLATED)
            self.assertEqual(archive.read('notes.slice/topic/note.md'), b'# Note\n')
        self.assertEqual(sorted(p.name for p in output.parent.iterdir()), ['notes.zip'])

    def test_tar_members(self):
        output = self.tmp / 'notes.tar.gz'
        write_archive(self.tree, output, 'tar.gz')
        self.assertEqual(output.read_bytes()[4:8], b'\0\0\0\0')  # gzip header mtime 0
        self.assertEqual(gzip.decompress(output.read_bytes())[257:265], b'ustar\x0000')  # POSIX, not GNU
        with tarfile.open(output) as archive:
            members = archive.getmembers()
            self.assertEqual([m.name for m in members], ['notes.slice', 'notes.slice/slice.toml', 'notes.slice/topic',
                                                         'notes.slice/topic/note.md'])
            for m in members:
                self.assertEqual((m.mtime, m.uid, m.gid, m.uname, m.gname), (0, 0, 0, '', ''), m.name)
                self.assertEqual(m.mode, 0o755 if m.isdir() else 0o644, m.name)
                self.assertEqual(m.isdir(), m.name in ('notes.slice', 'notes.slice/topic'), m.name)
            note = archive.getmember('notes.slice/topic/note.md')
            self.assertEqual(note.size, 7)
            self.assertEqual(archive.extractfile(note).read(), b'# Note\n')

    def test_root_name(self):
        for output, root in (('x.slice.zip', 'x.slice/'), ('X.ZIP', 'X.slice/'), ('y.tgz', 'y.slice/'),
                             ('z.TAR.GZ', 'z.slice/'), ('plain', 'plain.slice/')):
            path = self.tmp / 'names' / output
            fmt = 'zip' if output.lower().endswith('.zip') else 'tar.gz'
            write_archive(self.tree, path, fmt)
            if fmt == 'zip':
                with zipfile.ZipFile(path) as archive:
                    first = archive.namelist()[0]
            else:
                with tarfile.open(path) as archive:
                    first = archive.getnames()[0] + '/'
            self.assertEqual(first, root, output)

    def test_failure_leaves_neither_output_nor_temporary_file(self):
        output = self.tmp / 'new' / 'deeper' / 'notes.zip'  # missing parents are created
        with patch('mindslice.baking.archive.os.replace', side_effect=OSError('disk full')) as replace:
            with self.assertRaises(OSError):
                write_archive(self.tree, output, 'zip')
        temporary = Path(replace.call_args.args[0])
        self.assertEqual(temporary.parent, output.parent)  # beside the output, named so that gc recognises it
        self.assertTrue(TEMP_SLICE.fullmatch(temporary.name), temporary.name)
        self.assertEqual(list(output.parent.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
