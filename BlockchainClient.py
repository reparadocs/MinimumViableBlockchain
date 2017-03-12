from ecdsa import SigningKey, VerifyingKey
import binascii
import json
import hashlib
import threading
import requests
from threading import RLock

import time
import random

PROOF_OF_WORK = 4
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

def validate_transactions(transactions):
  for transaction in transactions:
    if not validate_transaction(transaction):
      print transaction
      return False
  return True

class BlockchainClient:
  def __init__(self, address):
    self.sk = SigningKey.generate()
    self.vk = self.sk.get_verifying_key()
    self.address = binascii.hexlify(self.vk.to_string())
    self.blockchain = []
    self.current_head = "0"
    self.clients = [address,]
    self.transaction_pool = []
    self.poollock = RLock()
    self.chainlock = RLock()

  def add_client(self, client):
    self.clients.append(client)
    client_blockchain = self.get_client_blockchain(client)
    if len(client_blockchain) <= len(self.blockchain):
      return
    if len(client_blockchain) > len(self.blockchain):
      inflated_cb = []
      for block in client_blockchain:
        i_block = Block(block["transaction"], block["previous"], self, block["nonce"], block["hash"])
        inflated_cb.append(i_block)
        if not i_block.validate():
          return
      if len(inflated_cb) > len(self.blockchain):
        with self.chainlock:
          self.blockchain = inflated_cb

  def get_client_blockchain(self, client):
    return json.loads(requests.get(client + '/blocks').text);

  def notify_clients(self, endpoint, data):
    for client in self.clients:
      requests.post(client + endpoint, data=data)

  def create_transaction(self, receiver, amount, fee=0.1):
    transaction = {
      "sender": self.address,
      "receiver": receiver,
      "amount": amount,
      "fee": fee,
    }
    transaction_dump = json.dumps(transaction)
    sig = self.sk.sign(transaction_dump)
    signed_transaction = {
      "signature": binascii.hexlify(sig),
      "transaction": transaction,
    }
    self.notify_clients('/new_transaction', {'transaction': json.dumps(signed_transaction)})
    return

  def transaction_signal(self, signed_transaction):
    with self.poollock:
      self.transaction_pool.append(json.loads(signed_transaction))

  def block_signal(self, block):
    # TODO: remove transactions from transaction pool
    block = json.loads(block)
    block = Block(block["transactions"], block["previous"], self, block["nonce"], block["hash"])
    if block.validate() and block.previous == self.current_head:
      self.current_head = block.hash
      with self.chainlock:
        self.blockchain.append(block)
    else:
      raise Exception

  def run_client(self):
    prev_pool = None
    while True:
      if len(self.transaction_pool) != 0:
        if prev_pool != self.transaction_pool:
          if validate_transactions(self.transaction_pool):
            prev_pool = self.transaction_pool
            block = Block(self.transaction_pool, self.current_head, self)
          else:
            raise Exception
        if block.hash_cycle():
          self.notify_clients('/new_block', {'block': json.dumps(block.to_dict())})
          print "I MINED IT " + block.hash
          self.transaction_pool = [] # VERY HACKY SOLUTION FIND A BETTER ONE

class Block:
  def __init__(self, transactions, previous, blockchain, nonce=0, v_hash=""):
    self.transactions = transactions
    self.previous = str(previous)
    self.nonce = nonce
    self.hash = v_hash
    self.blockchain = blockchain

  def __repr__(self):
    return str(self.to_dict())

  def serialize(self, include_hash=False):
    d = {
      "transactions": self.transactions,
      "previous": self.previous,
      "nonce": self.nonce
    }
    if include_hash:
      d["hash"] = self.hash 
    return d

  def to_dict(self):
    return self.serialize(True)

  def validate(self):
    if not validate_transactions(self.transactions):
      return False
    if self.hash[:PROOF_OF_WORK] != PROOF_OF_WORK_PREFIX:
      return False
    return hashlib.sha256(json.dumps(self.serialize())).hexdigest() == self.hash

  def hash_cycle(self):
    p_hash = hashlib.sha256(json.dumps(self.serialize())).hexdigest()
    if p_hash[:PROOF_OF_WORK] == PROOF_OF_WORK_PREFIX:
      self.hash = p_hash
      return True
    self.nonce += random.randint(1,100)
    return False
