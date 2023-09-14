from ast import literal_eval
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from inventory.models import Transaction

class TransactionOrderViewSet(ViewSet):
    serializer_class = TransactionOrderSerializer
    queryset = TransactionOrder.objects.all()

    def get_queryset(self):
        get = self.request.query_params.get('get')
        if get is not None:
            return TransactionOrder.objects.prefetch_related('transactions__stock_purchase__stocks__product', 'transactions__account').all()
        return super().get_queryset()

    # def get_serializer_class(self):
    #     get = self.request.query_params.get('get')
    #     if get is not None:
    #         return SimpleTransactionOrderSerializer
    #     return super().get_serializer_class()

    def update_account_balances(self, transaction):
        account = transaction.account
        account.credit += transaction.credit
        account.debit += transaction.debit
        account.save()

    def check_account_balances(self, transaction):
        if transaction.vouchar_type not in ['Purchase', 'Sales']:
            one = ['liability', 'revenue', 'equity'] # Laibility, Revenue, Equity
            two = ['assets', 'expense']  # Assets, Expense
            account = transaction.account
            if account.main_account in one:
                balance = account.credit - account.debit
            elif account.main_account in two:
                balance = account.debit - account.credit
            if balance < 0:
                raise serializers.ValidationError(
                    {
                        account.name: [
                            "Balance of this account is going to be negative"
                        ]
                    }
                )

    def save_transactions(self, main_transaction, transactions):
        for transaction in transactions:
            self.update_account_balances(transaction)

        for transaction in transactions:
            self.check_account_balances(transaction)

    def create(self, request, *args, **kwargs):
        try:
            req_data = ast.literal_eval(request.data)
        except:
            req_data = request.data
        mainTransaction = {"vouchar_type": req_data["vouchar_type"]}
        try:
            if req_data["transaction_date"]:
                mainTransaction["transaction_date"] = req_data["transaction_date"]
        except:
            pass
        debit = 0
        credit = 0
        transactions = []
        accounts = []
        try:
            req_transaction = ast.literal_eval(req_data["transactions"])
        except:
            req_transaction = req_data['transactions']
        for item in req_transaction:
            try:
                newItem = ast.literal_eval(item)
            except:
                newItem = item
            if newItem["account"] in accounts:
                raise serializers.ValidationError(
                    {
                        "Duplicate Entry": [
                            "Account Dual Entry in one transaction is not allowed."
                        ]
                    }
                )
            data = {
                "account": newItem["account"],
                "narration": newItem["narration"],
                "debit": newItem["debit"],
                "credit": newItem["credit"],
            }
            accounts.append(newItem["account"])
            debit += newItem["debit"]
            credit += newItem["credit"]
            transactions.append(data)

        vouchar_type = req_data["vouchar_type"]
        one = ['Cash Receipt', 'Bank Receipt']  # Receipts
        two = ['Cash Payment', 'Bank Payment']  # Payments
        if vouchar_type in two:
            if debit < credit:
                raise serializers.ValidationError(
                    {"Credit": ["Credit can't be more than Debit in Payment"]}
                )
            elif credit < debit:
                cashinhand = Account.objects.get(keyword='cashinhand')
                data = {
                    "account": cashinhand.id,
                    "debit": 0,
                    "credit": debit - credit,
                }
                transactions.append(data)
        elif vouchar_type in one:
            if debit > credit:
                raise serializers.ValidationError(
                    {"Debit": ["Debit can't be more than Credit in Payment"]}
                )
            elif credit > debit:
                cashinhand = Account.objects.get(keyword='cashinhand')
                data = {
                    "account": cashinhand.id,
                    "debit": credit - debit,
                    "credit": 0,
                }
                transactions.append(data)
                
        # # Creating Transactions     -------------------------------
        # transaction_serializer = CreateTransactionSerializer(data=transactions, many=True)
        # if transaction_serializer.is_valid():
        #     transactions = transaction_serializer.save(transaction_order=main_transaction)
        # else:
        #     return Response(transaction_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Save the transactions and check balances
        self.save_transactions(main_transaction, transactions)

        # Return serialized data to the user
        main_inctance = TransactionOrder.objects.prefetch_related(
            "transactions__stock_purchase__stocks__product",
            "transactions__account",
        ).get(id=main_transaction.id)
        serializer = SimpleTransactionOrderSerializer(main_inctance)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )
