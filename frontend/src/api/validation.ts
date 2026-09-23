import Ajv2020 from 'ajv/dist/2020';
import schemas from './schemas.json';

const ajv = new Ajv2020({ strict: false, allErrors: true });
ajv.addSchema(schemas);
export class ContractError extends Error {
  constructor(public schema: string) {
    super('Сервер жауабы API 1.0.0 келісіміне сәйкес емес. Командаға хабарласыңыз.');
  }
}
export function validate<T>(schema: string, data: unknown): T {
  const validator = ajv.getSchema(`qurylym-contract#/components/schemas/${schema}`);
  if (!validator?.(data)) throw new ContractError(schema);
  return data as T;
}
