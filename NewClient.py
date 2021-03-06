from flask import Flask, render_template, request
from BlockchainClient import BlockchainClient
import thread
import sys
import json
from flask_wtf import Form
from wtforms import TextField, IntegerField, SubmitField, validators, ValidationError

app = Flask(__name__)
app.secret_key = 's3cr3t'

if len(sys.argv) < 2:
  bk = BlockchainClient('http://localhost:5000', True)
else:
  bk = BlockchainClient('http://localhost:' + sys.argv[1])

class TransactionForm(Form):
  receiver = TextField("Receiver", [validators.Required("Please enter a receiver.")])
  amount = IntegerField("Amount", [validators.Required("Please enter an amount.")])
  submit = SubmitField("Send")

class ClientForm(Form):
  client = TextField("Client", [validators.Required("Please enter a client")])
  submit = SubmitField("Add Client")

@app.route("/blocks")
def blocks():
  # Get all blocks
  schain = []
  if len(bk.blockchain) > 0:
    schain.append(bk.blockchain[0])
    for block in bk.blockchain[1:]:
      schain.append(block.serialize(True))
  return json.dumps(schain)

@app.route("/create_transaction", methods=['POST'])
def create_transaction():
  # Post to create a transaction with this client with amount, receiver, and fee
  thread.start_new_thread(bk.create_transaction,(request.form['receiver'], int(request.form['amount'])))
  return "hello"

@app.route("/add_client", methods=['POST'])
def add_client():
  # Post to add a client
  if len(request.form['client']) > 2:
    thread.start_new_thread(bk.add_client, (request.form['client'],))
  return "hello"

@app.route("/new_block", methods=['POST'])
def new_block():
  # Post to notify of new block
  thread.start_new_thread(bk.block_signal,(request.form['block'], ))
  return "hello"

@app.route("/new_transaction", methods=['POST'])
def new_transaction():
  # Post to notify of new transaction
  thread.start_new_thread(bk.transaction_signal,(request.form['transaction'],))
  return "hello"

@app.route("/")
def index():
  form = TransactionForm()
  address = bk.address
  if bk.address in bk.bank:
    amount = bk.bank[bk.address]
  else:
    amount = 0
  return render_template('index.html', form=form, address=address, amount=amount)

@app.route("/clients")
def clients():
  form = ClientForm()
  clients = bk.clients
  return render_template('clients.html', form=form, clients=clients)

if __name__ == "__main__":
  thread.start_new_thread(bk.run_client,())
  port = None
  if len(sys.argv) >= 2:
    port = int(sys.argv[1])
  app.run(port=port)