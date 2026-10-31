"""Check network loading for trajectory exports without requiring Matplotlib."""

import gzip
import tempfile
import unittest
from pathlib import Path

from sumo_experiment.plot_mobility import read_roads


class MobilityNetworkTests(unittest.TestCase):
    """Grid and city exports must read the same road-shape representation."""

    def test_grid_and_compressed_city_roads(self) -> None:
        """Read visible roads and exclude internal junction lanes in both formats."""

        xml = (b'<net><edge id="road"><lane shape="0,0 20,30"/></edge>'
               b'<edge id=":junction" function="internal"><lane shape="1,1 2,2"/></edge></net>')
        for filename in ("grid.net.xml", "city.net.xml.gz"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                network = output / "network"
                network.mkdir()
                path = network / filename
                path.write_bytes(gzip.compress(xml) if path.suffix == ".gz" else xml)
                self.assertEqual(read_roads(output), [[(0.0, 0.0), (20.0, 30.0)]])


if __name__ == "__main__":
    unittest.main()
