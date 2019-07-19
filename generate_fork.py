import argparse
import logging
import shutil

from testchain.motifs.general import SetupChain, FinalizeChain
from testchain.motifs.change import Change
from testchain.motifs.motifs import Motifs
from testchain.motifs.addresses import Addresses
from testchain.motifs.special import SpecialCases
from testchain.motifs.taint import Taint
from testchain.motifs.heuristics import Heuristics
from testchain.motifs.cash import BitcoinCash
from testchain.runner import Runner


parser = argparse.ArgumentParser(description='Generate a synthetic blockchain.')
parser.add_argument('--output-dir', dest='output_dir', default="../files/", help='Output directory')
parser.add_argument('--node-dir', dest='node_dir', default="/home/martin/testchains/nodedir", help='Node data directory')
parser.add_argument('--chain', dest='chain', default="btc", help='Chain [btc, bch]')
parser.add_argument('--exec', dest='exec', default="bitcoind", help="Path to bitcoind executable")
parser.add_argument('-d', '--debug', help="Print debugging statements",
                    action="store_const", dest="log_level", const=logging.DEBUG, default=logging.INFO)

args = parser.parse_args()

node_dir = args.node_dir

shared_dir = node_dir + "/shared"

# create a chain that is used as the shared common history
runner_shared = Runner(
    output_dir=args.output_dir,
    chain=args.chain,
    executable=args.exec,
    node_dir=shared_dir,
    log_level=args.log_level
)

runner_shared.add_generator(SetupChain)
runner_shared.add_generator(Addresses)
runner_shared.add_generator(Motifs)
runner_shared.add_generator(Change)
runner_shared.add_generator(SpecialCases)
runner_shared.add_generator(Taint)
runner_shared.add_generator(Heuristics)
runner_shared.add_generator(BitcoinCash)
runner_shared.add_generator(FinalizeChain)

runner_shared.run()

# copy the shared chain files to the node directory of the "main" chain
node_dir_main = node_dir + "/btc-main"
shutil.copytree(shared_dir, node_dir_main)

# copy the shared chain files to the node directory of the "fork" chain
node_dir_fork = node_dir + "/btc-fork"
shutil.copytree(shared_dir, node_dir_fork)

# create the "main" chain that builds upon the shared chain
runner_main = Runner(
    output_dir=args.output_dir,
    chain=args.chain,
    executable=args.exec,
    node_dir=node_dir_main,
    log_level=args.log_level,
    current_time=runner_shared.current_time
)

runner_main.add_generator(SetupChain)
runner_main.add_generator(Addresses)
runner_main.add_generator(Motifs)
runner_main.add_generator(Change)
runner_main.add_generator(SpecialCases)
runner_main.add_generator(Taint)
runner_main.add_generator(Heuristics)
runner_main.add_generator(BitcoinCash)
runner_main.add_generator(FinalizeChain)

runner_main.run()

# create the "fork" chain that builds upon the shared chain
runner_fork = Runner(
    output_dir=args.output_dir,
    chain=args.chain,
    executable=args.exec,
    node_dir=node_dir_fork,
    log_level=args.log_level,
    current_time=runner_shared.current_time
)

runner_fork.add_generator(SetupChain)
runner_fork.add_generator(Addresses)
runner_fork.add_generator(Motifs)
runner_fork.add_generator(Change)
runner_fork.add_generator(SpecialCases)
runner_fork.add_generator(Taint)
runner_fork.add_generator(Heuristics)
runner_fork.add_generator(BitcoinCash)
runner_fork.add_generator(FinalizeChain)

runner_fork.run()
