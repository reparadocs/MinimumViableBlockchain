from ecdsa import SigningKey, VerifyingKey
import binascii
import json
import hashlib
import threading
import requests
import time

REQUEST_URL = "http://localhost:5000/signals"
REQUEST_URL_SIGNAL = "http://localhost:5000/signal/"

PROOF_OF_WORK = 2
PROOF_OF_WORK_PREFIX = "0" * PROOF_OF_WORK
# How do we know how much each participant has without traversing the entire blockchain?
# How do offline participants get the blockchain?
# If multiple blocks broadcasted how many branches do we keep track of and for how long?

def signal(dump):
  r = requests.post(REQUEST_URL, data={"signal": dump})

def validate_transaction(signed_transaction):
  transaction = signed_transaction["transaction"]
  signature = binascii.unhexlify(signed_transaction["signature"])
  s_vk = VerifyingKey.from_string(binascii.unhexlify(transaction["sender"]))
  transaction_dump = json.dumps(transaction)
  return s_vk.verify(signature, transaction_dump)

class BlockchainClient:
  def __init__(self):
    self.sk = SigningKey.generate()
    self.vk = self.sk.get_verifying_key()
    self.address = binascii.hexlify(self.vk.to_string())
    self.blockchain = []
    self.current_head = "0"

  def create_transaction(self, receiver, amount):
    transaction = {
      "sender": self.address,
      "receiver": receiver,
      "amount": amount,
    }
    transaction_dump = json.dumps(transaction)
    sig = self.sk.sign(transaction_dump)
    signed_transaction = {
      "signature": binascii.hexlify(sig),
      "transaction": transaction,
    }
    message = {"type":"transaction", "content": signed_transaction}
    signal(json.dumps(message))

  def transaction_signal(self, signed_transaction):
    head = self.current_head
    signature = signed_transaction["signature"]
    block = Block(signed_transaction, head)
    block.mine()
    if head == self.current_head:
      message = {"type":"block", "content": block.to_dict()}
      signal(json.dumps(message))

  def block_signal(self, block):
    block = Block(block["transaction"], block["previous"], block["nonce"], block["hash"])
    if block.validate() and block.previous == self.current_head:
      self.current_head = block.hash
      self.blockchain.append(block)
    else:
      raise Exception

class Block:
  def __init__(self, transaction, previous, nonce=0, v_hash=""):
    self.transaction = transaction
    self.previous = str(previous)
    self.nonce = nonce
    self.hash = v_hash

  def to_dict(self):
    return {"transaction": self.transaction, "previous": self.previous, "nonce": self.nonce, "hash": self.hash}

  def validate(self):
    if self.hash[:PROOF_OF_WORK] != PROOF_OF_WORK_PREFIX:
      return False
    block = {
      "transaction": self.transaction,
      "previous": self.previous,
      "nonce": self.nonce
    }
    return hashlib.sha256(json.dumps(block)).hexdigest() == self.hash

  def mine(self):
    if validate_transaction(self.transaction):
      self.find_hash()
    else:
      raise Exception

  def find_hash(self):
    while True:
      block = {
        "transaction": self.transaction,
        "previous": self.previous,
        "nonce": self.nonce
      }
      p_hash = hashlib.sha256(json.dumps(block)).hexdigest()
      if p_hash[:PROOF_OF_WORK] == PROOF_OF_WORK_PREFIX:
        self.hash = p_hash
        break
      self.nonce += 1

def get_signal(bk, signal_id):
  r = requests.get(REQUEST_URL_SIGNAL + str(signal_id))
  d = json.loads(r.text)
  print "received " + d["type"] + " signal"
  if d["type"] == "manual":
    if d["address"] == bk.address:
      bk.create_transaction(d["receiver"], int(d["amount"]))
      return
  if d["type"] == "block":
    bk.block_signal(d["content"])
  elif d["type"] == "transaction":
    bk.transaction_signal(d["content"])

def main():
  bk = BlockchainClient()
  last_signal = 0
  print bk.address
  while True:
    r = requests.get(REQUEST_URL)
    s_l = int(r.text)
    while last_signal < s_l:
      t = threading.Thread(target=get_signal, args=(bk, last_signal,))
      t.start()
      last_signal += 1
    time.sleep(1)

main()
