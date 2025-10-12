import sys


def compute_transfer_topic():
    # Try Web3.keccak first
    try:
        from web3 import Web3
        print(Web3.keccak(text="Transfer(address,address,uint256)").hex())
        return
    except Exception:
        pass

    # Try eth_utils.keccak
    try:
        from eth_utils import keccak
        try:
            print(keccak(text="Transfer(address,address,uint256)").hex())
            return
        except TypeError:
            print(keccak(b"Transfer(address,address,uint256)").hex())
            return
    except Exception:
        pass

    # Final fallback constant
    print("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")


if __name__ == "__main__":
    compute_transfer_topic()
