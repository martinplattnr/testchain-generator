import atexit
import json
import logging
import os
import shutil
import subprocess
import tempfile
from time import sleep
from typing import List, Type

import bitcointx
import bitcointx.rpc
from testchain.generator import Generator
from testchain.address import COINBASE_KEY
from testchain.util import DisjointSet

bitcointx.SelectParams('regtest')


class Runner(object):
    motif_generators: List[Generator]

    def __init__(self, output_dir, chain, executable, log_level, node_dir=None, current_time=1535760000):
        self.chain = chain
        self.exec = executable
        self.node_dir = node_dir
        self.log_level = log_level
        self.current_time = current_time
        self.prev_block = None
        self.motif_generators = []
        self.kv = {}
        self.cospends = DisjointSet()
        self.output_dir = os.path.join(output_dir, '')
        self._setup_logger()
        self._setup_chain_params()
        self._setup_bitcoind()
        self.proxy = bitcointx.rpc.Proxy(btc_conf_file=self.conf_file)
        self.proxy.call("importprivkey", COINBASE_KEY)

    def _setup_logger(self):
        self.log = logging.getLogger(__name__)
        self.log.setLevel(self.log_level)
        # todo: log setup can be improved, eg. inject config from the calling file (generate_*.py)
        if not self.log.hasHandlers():
            ch = logging.StreamHandler()
            ch.setLevel(self.log_level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.log.addHandler(ch)
        self.log.info("Setting log level to " + logging.getLevelName(self.log_level))

    def _setup_chain_params(self):
        # set up chainspecific
        if self.chain == "ltc":
            from testchain.util import CoreLitecoinParams, RegtestLitecoinParams
            bitcointx.SelectAlternativeParams(CoreLitecoinParams, RegtestLitecoinParams)

    def _setup_bitcoind(self):
        if self.node_dir:
            if not os.path.isdir(self.node_dir):
                raise NotADirectoryError("The node_dir directory does not exist.")
        else:
            self.node_dir = tempfile.TemporaryDirectory().name

        self.log.info("Using node directory {}".format(self.node_dir))

        if self.chain == "btc" or self.chain == "bch":
            filename = "bitcoin.conf"
        elif self.chain == "ltc":
            filename = "litecoin.conf"
        else:
            raise ValueError("Unkown chain. Please add an entry for the config file name.")

        # copy conf file to temp dir
        self.conf_file = self.node_dir + "/" + filename
        self.log.info("Config file created at {}".format(self.conf_file))
        shutil.copy("bitcoin.conf", self.conf_file)

        # launch bitcoind
        params = [self.exec, "-rpcport=18443", "-datadir={}".format(self.node_dir),
                  "-mocktime={}".format(self.current_time), "-reindex"]

        # Disable Bitcoin Cash specific address format (breaks Python library)
        # Enable CTOR
        if self.chain == "bch":
            params += ["-usecashaddr=0", "-magneticanomalyactivationtime=0"]

        self.log.info("Executing {}".format(params))
        self.proc = subprocess.Popen(params, stdout=subprocess.DEVNULL)

        # kill process when generator is done
        atexit.register(self._terminate)

        self.log.info("Waiting 10 seconds for node to start")
        sleep(10)

    def _terminate(self):
        """
        Kills the bitcoind process
        """
        if self.proc.poll() is None:
            sleep(1)
            self.log.info("Waiting 30 seconds for node to quit")
            self.proc.terminate()
            self.proc.wait(30)
            self.log.info("Node has terminated")

    def next_timestamp(self):
        self.current_time += 600
        return self.current_time

    def export_address_counts(self):
        self._address_sanity_check()
        counts = {"p2pkh": 2, "p2wpkh": 0, "p2sh": 0, "p2wsh": 0}  # coinbase addresses
        for g in self.motif_generators:
            for addr in g.addresses:
                counts[addr.type] += 1
        self.kv["p2pkh_address_count"] = counts["p2pkh"]
        self.kv["p2wpkh_address_count"] = counts["p2wpkh"]
        self.kv["p2sh_address_count"] = counts["p2sh"]
        self.kv["p2wsh_address_count"] = counts["p2wsh"]

    def _address_sanity_check(self):
        total_addresses = 0
        unique_addresses = set()
        for g in self.motif_generators:
            key_indices = [x.key_index for x in g.addresses]
            unique_addresses |= set(key_indices)
            total_addresses += len(key_indices)
        if len(unique_addresses) != total_addresses:
            self.log.warning("Addresses are not unique.")

    def copy_blk_file(self, truncate_file=True):
        """
        Copies the first blk file from the regtest directory to the output directory
        :param truncate_file: Whether the final block file should be truncated. Works with BlockSci, but may not work
        when using other parsers.
        """
        blk_destination = self.output_dir + self.chain + "/regtest/blocks/"
        self.log.info("Copying blk00000.dat to {}".format(blk_destination))
        if not os.path.exists(blk_destination):
            os.makedirs(blk_destination)
        source = "{}/regtest/blocks/blk00000.dat".format(self.node_dir)

        if truncate_file:
            with open(source, "rb") as f:
                with open(blk_destination + "blk00000.dat", "wb") as dest:
                    counter = 0
                    while True:
                        bts = f.read(16)
                        if not bts or counter == 16:
                            break
                        if bts == b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00':
                            counter += 1
                        else:
                            counter = 0
                        dest.write(bts)
        else:
            shutil.copy(source, blk_destination)

    def prepare_output_dir(self):
        dest_dir = self.output_dir + self.chain + "/"
        if not os.path.exists(dest_dir):
            os.mkdir(dest_dir)
        return dest_dir

    def persist_hashes(self):
        """
        Dumps hashes into JSON file.
        """
        # kv = {}
        # for g in self.motif_generators:
        #     kv = {**kv, **g.stored_hashes}

        self.log.info("Writing hashes to file output.json")
        self.log.debug(self.kv)
        dest_dir = self.prepare_output_dir()
        with open(dest_dir + "output.json", "w") as f:
            json.dump(self.kv, f, indent=4)

    def persist_cospends(self):
        self.log.info("Writing cospent addresse to file cospends.txt")
        dest_dir = self.prepare_output_dir()
        with open(dest_dir + "cospends.txt", "w") as f:
            for s in self.cospends.all():
                f.write(",".join(s))
                f.write("\n")

    def add_generator(self, generator: Type[Generator]):
        gen = generator(self.proxy, self.chain, self.log, self.kv, (len(self.motif_generators) + 1) * 10000,
                        self.next_timestamp, self.cospends)
        self.log.debug("Magic No: {}".format(gen.offset))
        self.motif_generators.append(gen)

    def run(self):
        startBlockHeight = self.proxy.call("getblockcount")
        self.log.info("### Starting with a chain of " + str(startBlockHeight) + " blocks")

        for g in self.motif_generators:
            self.log.info("Starting generator " + type(g).__name__ + " (Block height: " + str(self.proxy.call("getblockcount")) + ")")
            g.run()

        self._address_sanity_check()
        self.copy_blk_file()
        self.persist_hashes()
        self.persist_cospends()

        endBlockHeight = self.proxy.call("getblockcount")
        self.log.info("### Finishing with a chain of " + str(endBlockHeight) + " blocks, generated " + str(endBlockHeight - startBlockHeight) + " blocks")

        self._terminate()

