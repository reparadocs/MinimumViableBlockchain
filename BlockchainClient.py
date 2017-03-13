from ecdsa import SigningKey, VerifyingKey
import binascii
import json
import hashlib
import threading
import requests
from threading import RLock

import time
import random

COINBASE_AMOUNT = 100
PROOF_OF_WORK = 5
PROOF_OF_WORK_PREFIX = "0" * PROOF_OF_WORK

def signal(dump):
  r = requests.post(REQUEST_URL, data={"signal": dump})

def validate_transaction(signed_transaction, bank):
  transaction = signed_transaction["transaction"]
  if bank:
    if transaction["sender"] not in bank:
      return False
    if bank[transaction["sender"]] < transaction["amount"] + transaction["fee"]:
      return False
  signature = binascii.unhexlify(signed_transaction["signature"])
  s_vk = VerifyingKey.from_string(binascii.unhexlify(transaction["sender"]))
  transaction_dump = json.dumps(transaction)
  return s_vk.verify(signature, transaction_dump)

def validate_transactions(transactions, bank):
  for transaction in transactions:
    if not validate_transaction(transaction, bank):
      return False
  return True

def setup_bank(blockchain):
  bank = {blockchain[0]: COINBASE_AMOUNT}
  for block in blockchain[1:]:
    for transaction in block.transactions:
      transaction = transaction["transaction"]
      bank[transaction["sender"]] -= transaction["amount"] + transaction["fee"]
      if bank[transaction["sender"]] < 0:
        raise Exception
      if transaction["receiver"] in bank:
        bank[transaction["receiver"]] += transaction["amount"]
      else:
        bank[transaction["receiver"]] = transaction["amount"]
      if block.miner in bank:
        bank[block.miner] += transaction["fee"]
      else:
        bank[block.miner] = transaction["fee"]
  return bank

class BlockchainClient:
  def __init__(self, address, coinbase = False):
    self.sk = SigningKey.generate()
    self.vk = self.sk.get_verifying_key()
    self.address = binascii.hexlify(self.vk.to_string())
    if coinbase:  
      self.blockchain = [self.address,]
    else:
      self.blockchain = []
    self.current_head = "0"
    self.clients = [address,]
    self.transaction_pool = []
    self.poollock = RLock()
    self.chainlock = RLock()
    self.banklock = RLock()
    if coinbase:
      self.bank = {self.address: COINBASE_AMOUNT}
    else:
      self.bank = {}

  def add_client(self, client):
    self.clients.append(client)
    client_blockchain = self.get_client_blockchain(client)
    if len(client_blockchain) <= len(self.blockchain):
      return
    if len(client_blockchain) > len(self.blockchain):
      inflated_cb = [client_blockchain[0],]
      for block in client_blockchain[1:]:
        i_block = Block(block["transactions"], block["previous"], None, block["miner"], block["nonce"], block["hash"])
        inflated_cb.append(i_block)
        if not i_block.validate():
          return

      cb_bank = setup_bank(inflated_cb)
        
      if len(inflated_cb) > len(self.blockchain):
        with self.chainlock:
          self.blockchain = inflated_cb
          if len(inflated_cb) != 1:
            self.current_head = self.blockchain[-1].hash
        with self.banklock:
          self.bank = cb_bank
            

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
    if self.bank[self.address] < amount + fee:
      raise Exception
    transaction_dump = json.dumps(transaction)
    sig = self.sk.sign(transaction_dump)
    signed_transaction = {
      "signature": binascii.hexlify(sig),
      "transaction": transaction,
    }
    self.notify_clients('/new_transaction', {'transaction': json.dumps(signed_transaction)})
    return

  def transaction_signal(self, signed_transaction):
    i_st = json.loads(signed_transaction)
    if not validate_transaction(i_st, self.bank):
      return 

    total_due = 0
    for transaction in self.transaction_pool:
      if transaction["transaction"]["sender"] == i_st["transaction"]["sender"]:
        total_due += transaction["transaction"]["amount"] + transaction["transaction"]["fee"]

    if total_due > self.bank[i_st["transaction"]["sender"]]:
      return 

    with self.poollock:
      self.transaction_pool.append(i_st)

  def block_signal(self, block):
    block = json.loads(block)
    block = Block(block["transactions"], block["previous"], self.bank, block["miner"], block["nonce"], block["hash"])
    if block.validate() and block.previous == self.current_head:
      with self.banklock:
        for transaction in block.transactions:
          transaction = transaction["transaction"]
          self.bank[transaction["sender"]] -= transaction["amount"] + transaction["fee"]
          if self.bank[transaction["sender"]] < 0:
            raise Exception
          if transaction["receiver"] in self.bank:
            self.bank[transaction["receiver"]] += transaction["amount"]
          else:
            self.bank[transaction["receiver"]] = transaction["amount"]
          if block.miner in self.bank:
            self.bank[block.miner] += transaction["fee"]
          else:
            self.bank[block.miner] = transaction["fee"]
      with self.chainlock:
        self.current_head = block.hash
        self.blockchain.append(block)
      new_pool = []
      with self.poollock:
        for transaction in self.transaction_pool:
          if transaction not in block.transactions:
            new_pool.append(transaction)
        self.transaction_pool = new_pool
    else:
      raise Exception

  def run_client(self):
    prev_pool = None
    while True:
      if len(self.transaction_pool) != 0:
        if prev_pool != self.transaction_pool:
          if validate_transactions(self.transaction_pool, self.bank):
            prev_pool = self.transaction_pool
            block = Block(self.transaction_pool, self.current_head, self.bank, self.address)
          else:
            raise Exception
        if block is not None and block.hash_cycle():
          self.notify_clients('/new_block', {'block': json.dumps(block.to_dict())})
          block = None
          print "I MINED IT " 

class Block:
  def __init__(self, transactions, previous, bank, miner, nonce=0, v_hash=""):
    self.transactions = transactions
    self.previous = str(previous)
    self.nonce = nonce
    self.hash = v_hash
    self.bank = bank
    self.miner = miner

  def __repr__(self):
    return str(self.to_dict())

  def serialize(self, include_hash=False):
    d = {
      "transactions": self.transactions,
      "previous": self.previous,
      "nonce": self.nonce,
      "miner": self.miner,
    }
    if include_hash:
      d["hash"] = self.hash 
    return d

  def to_dict(self):
    return self.serialize(True)

  def validate(self):
    if not validate_transactions(self.transactions, self.bank):
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
