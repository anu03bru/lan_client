import tempfile
import unittest
import zipfile
from pathlib import Path

from lanparty.download import expand_path, extract_matching, file_name_from_url, remove_path


class DownloadHelperTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_file_name_from_url(self):
        self.assertEqual(file_name_from_url("https://x/releases/download/1.5/stk-1.5.exe"), "stk-1.5.exe")
        sourceforge = "https://sourceforge.net/projects/blobby/files/x/1.1.1/blobby2-win32-1.1.1.zip/download"
        self.assertEqual(file_name_from_url(sourceforge), "blobby2-win32-1.1.1.zip")

    def test_expand_path(self):
        variables = {"APPDATA": "C:/Users/a/AppData/Roaming"}
        self.assertEqual(expand_path("%APPDATA%/0ad", variables, self.root), Path("C:/Users/a/AppData/Roaming/0ad"))
        self.assertEqual(expand_path("~/OdamexLAN", {}, self.root), self.root / "OdamexLAN")
        with self.assertRaises(ValueError):
            expand_path("%NOPE%/x", variables, self.root)

    def test_extract_matching_copies_flat(self):
        zip_path = self.root / "freedm.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("freedm-0.13.0/freedm.wad", "wad")
            archive.writestr("freedm-0.13.0/README.txt", "text")
        dest = self.root / "wads"
        self.assertEqual(extract_matching(zip_path, "*.wad", dest), "freedm.wad")
        self.assertEqual([path.name for path in dest.iterdir()], ["freedm.wad"])
        with self.assertRaises(ValueError):
            extract_matching(zip_path, "*.pk3", dest)

    def test_remove_path(self):
        folder = self.root / "data"
        (folder / "sub").mkdir(parents=True)
        self.assertIsNone(remove_path(folder))
        self.assertFalse(folder.exists())
        self.assertEqual(remove_path(folder), "not found, nothing to do")


if __name__ == "__main__":
    unittest.main()
